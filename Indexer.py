from Model import *
import sqlite3
from bs4 import Comment
from bs4 import BeautifulSoup
from nltk.stem.porter import *
from nltk.corpus import stopwords


class Indexer:

    def __init__(self):
        pass

    def update(self,url,content):

        #delete old entries of this url (if exists any)
        self._deleteOldEntries(url)

        # for phrase search
        #try:
        document,title = self.phraseParser(url,content)
        #except:
           # print("FUCK!!!")
        pass
        if title is None:
            title = url
        pass
        self.addToFullPages(document, url,title.strip())

        bulkEntries = []

        #Stemmer
        stemmer = PorterStemmer()

        #parse the web page content
        wordIndexes, wordImportance = self.parser(content)

        #insert page extracted words in a list for bulk db insertions
        for word in wordImportance:

            ##avoiding alphaNum words...
            if word in wordIndexes: #and not re.search('\d+',word):
                stemmed  = stemmer.stem(word)
                bulkEntries.append({'keyword' : word ,'stem': stemmed, 'url': url, 'positions' : wordIndexes[word], 'importance':wordImportance[word]})

        if(bulkEntries):
            #insert new entries in IndexerTable...Fastest way!
            with DBIndexer.atomic():
                #sqlite max vars = 999 per bulk insertion
                size = (999 // len(bulkEntries[0]))
                for i in range(0, len(bulkEntries), size):
                    while True:
                        try:
                            IndexerTable.insert_many(bulkEntries[i:i + size]).upsert().execute()
                            break

                        except (OperationalError, sqlite3.OperationalError) as e:
                            if 'binding' in str(e):
                                break
                            print('INDEXER: Database busy, retrying. bulk Insertions')
                        except:
                            break
            print("Inserted:",len(bulkEntries),"new entries for url:",url)

    def addToFullPages(self,content,url,title):

        while True:
            try:
                FullPages.create(pageURL=url, pageContent=content, pageTitle=title).update()
                break
            except (OperationalError, sqlite3.OperationalError) as e:
                if 'binding' in str(e):
                    break
                print('INDEXER: Database busy, retrying. FullPages Insertion')
            #except:
                #print("FUCKK")
                #break

    def _deleteOldEntries(self,url):

        query = IndexerTable.delete().where(IndexerTable.url == url)
        pquery = FullPages.delete().where(FullPages.pageURL == url)
        pquery.execute()
        print("Deleted:", query.execute(), "old entries for url:",url)


    '''inserts a new entry(keyword,url)'''
    def _addToIndex(self, keyword, url, pos = [], importance = 2):

        try:
            IndexerTable.create(keyword= keyword , url = url, positions = pos, importance = importance).update()

        except IntegrityError: # keyword & url already exists!
            return -1

        return 1


    '''Searching with words...IN: list of keywords, OUT: dict[keyword] of urls'''
    def lookupWithWords(self, keywords = []):

        result = {}
        for word in keywords:
            urlList = []
            try:
                resultQuery = IndexerTable.select(IndexerTable.url).where(IndexerTable.keyword == word)
                for x in resultQuery:
                    urlList.append(x.url)

            except IndexerTable.DoesNotExist:
                urlList.append(-1)

            result.update({word: urlList})

        return result


    '''getting keywords with urls...IN: list of urls, OUT: dict[url] of keywords'''
    def lookupWithPages(self, pages=[]):

        result = {}
        for pg in pages:
            wordList = []
            try:
                resultQuery = IndexerTable.select(IndexerTable.keyword).where(IndexerTable.url == pg)
                for x in resultQuery:
                    wordList.append(x.keyword)

            except IndexerTable.DoesNotExist:
                wordList.append(-1)

            result.update({pg: wordList})

        return result


    '''-----------------------------------Parsing functions----------------------------------------------------------'''

    '''IN:[word1, word2, ...], OUT:{word1: [pos1, pos2], word2: [pos2, pos3], ...}'''
    def _indexFile(self,wordList):

        fileIndex = {}
        for index, word in enumerate(wordList):
            if word in fileIndex.keys():
                fileIndex[word].append(index)
            else:
                fileIndex[word] = [index]
        return fileIndex


    def _assignImportance(self,keywords,count,imp,importanceMap = {}):

        for word in keywords:
            if not (word in importanceMap):
                importanceMap[word]= imp
                count+=1

    '''removes text in scripts and comments'''
    def _visibleText(self,element):

        if element.parent.name in ['style', 'script', 'link', '[document]']:
            return False
        elif re.match('.*<!--.*-->.*', str(element)):
            return False

        return True


    def _parseKeywords(self,text):

        for i in range(len(text)):
            pattern = re.compile('[\W_]+')
            text[i] = pattern.sub(' ', text[i])
            re.sub(r'[\W_]+', '', text[i])
            text[i] = text[i].lower()
            text += text[i].split()
            text[i] = None

        return text


    def _removeStopWords(self,wordList):

        stop = set(stopwords.words('english'))
        wordList = [word for word in wordList if word not in stop and len(word) > 2]
        return wordList


    def _initParser(self,text):

        soup = BeautifulSoup(text, 'html.parser')

        # ---------------Finding Comments to remove them---------------
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        [comment.extract() for comment in comments]

        # ---------------Getting Text without Comments-------------------
        texts = soup.find_all(text=True)

        # ---------------removing the unwanted script and links from the doc and returning list of words------------
        visibleTexts = filter(self._visibleText, texts)

        # ---------------remove all symbols like #$%@ , spaces and newlines--------------
        parsedWords = self._parseKeywords(list(visibleTexts))
        parsedWords = [word for word in parsedWords if word is not ' ' and word is not None]
        # remove stop words
        parsedWords = self._removeStopWords(parsedWords)


        return parsedWords

    '''parsing an html doc'''
    def parser(self, htmlDoc):

        soup = BeautifulSoup(htmlDoc, 'html.parser')
        count = 0
        importMap ={}

        #-----------------parsing Title and assigning its importance map----------------
        if(soup.title and soup.title.string is not None):
            title = self._initParser(str(soup.title))

            self._assignImportance(title,count,0,importMap)

        #parsing headers
        headers = [soup.h1 , soup.h2 , soup.h3 , soup.h4
                       , soup.h5 , soup.h6]

        headers = [str(x) for x in headers if x is not None]
        #print(headers)

        headers = self._initParser(' '.join(headers))
        self._assignImportance(headers, count, 1, importMap)

        #---------------------parsing  plain text---------------------
        plainText = self._initParser(htmlDoc)
        self._assignImportance(plainText,count,2,importMap)

        # --------------indexing words -------------
        indexMap = self._indexFile(plainText)


        return indexMap,importMap

    def phraseParser(self,url,text):

        soup = BeautifulSoup(text, 'html.parser')
        title = None
        if (soup.title and soup.title.string is not None):
        #try:
            title = soup.title.string
        #except:
         #   print("AAA")
        #print(title)
        if(title is None):
            # parsing headers
            headers = [soup.h1, soup.h2, soup.h3, soup.h4
            , soup.h5, soup.h6]

            headers = [str(x) for x in headers if x is not None]
            #print(headers)
            for header in headers:
                #print(header)
                soupy = BeautifulSoup(header, 'html.parser')
                comments = soupy.findAll(text=lambda text: isinstance(header, Comment))
                [comment.extract() for comment in comments]
                texts = soupy.find_all(text=True)
                header = filter(self._visibleText, texts)
                header = list(header)
                if len(header) == 1:
                    title = header[0]
                    break
                if(header):
                    title = header[0]
            pass
        #print(soup.get_text())

        # ---------------Finding Comments to remove them---------------
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        [comment.extract() for comment in comments]

        # ---------------Getting Text without Comments-------------------
        texts = soup.find_all(text=True)

        # ---------------removing the unwanted script and links from the doc and returning list of words------------
        visibleTexts = filter(self._visibleText, texts)


        #thefile.close()'''
        # ---------------remove all symbols like #$%@ , spaces and newlines--------------
        parsedWords = self._parseKeywords(list(visibleTexts))
        parsedWords = [word for word in parsedWords if word is not ' ' and word is not None]
        pass #extra spaces!
        space = ' '
        document = space.join(parsedWords)

        visibleTexts = filter(self._visibleText, texts)
        waw = list(visibleTexts)
        listy = [x.strip() for x in waw if x.strip() is not '' and x is not None]
        fname = url.replace("/", "")
        #with open(fname + '.txt', 'w') as thefile:
        #    # print(str(visibleTexts))
        #    for item in listy:
        #        s = item
        #        print('s:', s)
        #        thefile.write("%s\n" % s)



        print(title)
        return document, title
