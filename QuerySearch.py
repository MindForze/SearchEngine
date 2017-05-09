from nltk.stem.porter import *
from nltk.corpus import stopwords
from Model import PageRank, IndexerTable, FullPages,QuerySuggestion, \
    DBIndexer, DBPageRank, DBPhrase, DBQuery
import math
import sqlite3
from peewee import OperationalError

...
WORDLIMIT = 20
# DBIndexer.connect()
# DBPageRank.connect()
# DBPhrase.connect()
DBQuery.connect()

if not DBQuery.get_tables():
    print("Creating Query Database...")
    DBQuery.create_tables([QuerySuggestion])
...

class QuerySearch:

    def __init__(self, query):

        self.rankTextResults = {} #url:score
        self.rankPhraseResults = {}  # url:score
        self.rankAllResults = {}

        self.query, self.stemmedQuery, self.isPhrase, \
        self.phraseQuery, self.queryStr, self.trimmedSearch = self.queryProcessor(query)

        #print(self.query)
        #print(self.phraseQuery)
        #print(self.isPhrase)
        #print(self.trimmedSearch)'''


    def getSearchResult(self):

        if self.trimmedSearch:
            print("Search was trimmed to first %d words" %WORDLIMIT)

        self.phraseSearch()
        self.textSearch()

        mutualPages = self.rankPhraseResults.keys() & self.rankTextResults.keys()

        if self.isPhrase:
            for page in mutualPages:
                self.rankPhraseResults[page] += self.rankTextResults[page]
                del self.rankTextResults[page]

            mainResult = self._sortAndSave(self.rankPhraseResults.items(),'0')
            print("About %d search with \"phrase\" results:" % len(mainResult))
            print(mainResult)
            compResult = self._sortAndSave(self.rankTextResults.items(),'1')
            if(compResult):
                print("About %d related results:" % len(compResult))
                print(compResult)
            return mainResult, compResult

        else:
            for page in mutualPages:
                self.rankTextResults[page] += self.rankPhraseResults[page]
                del self.rankPhraseResults[page]
            mainResult = self._sortAndSave(self.rankTextResults.items(),'0')
            print("About %d search results:" % len(mainResult))
            print(mainResult)
            compResult = self._sortAndSave(self.rankPhraseResults.items(),'1')
            if (compResult):
                print("About %d  related results:" % len(compResult))
                print(compResult)
            return mainResult, compResult


    def _sortAndSave(self, sortable,s="x",save = False):
        # sort and ret list of urls
        tupleList = sorted(sortable, key=lambda x: x[1], reverse=True)
        listy = [tupleList[x][0] for x in range(len(tupleList))]

        # save to file for sanity check
        if save:
            thefile = open(s + self.queryStr[0:50] + '.txt', 'w')
            for item in tupleList:
                thefile.write("%s\n" % str(item))

        return listy

    '''sets all query related variables for searching'''
    def queryProcessor(self, query):

        query1 = str(query).strip()
        # phrase if "text"
        phraseQuery = re.findall('"([^"]*)"', query1)
        isPhrase = True if phraseQuery else False
        pattern = re.compile(r'[\W_]+')
        query2 = pattern.sub(' ', query1).lower()
        #print(query)
        queryStr = query2
        #print(queryStr)
        #rm stop words for text search
        queryList = self._removeStopWords(query.split())

        #size validation
        trimmedSearch = False
        if (len(queryList) > WORDLIMIT):
            queryList = queryList[:WORDLIMIT]
            trimmedSearch = True

        stemmedQuery = self._porterStemmer(queryList)

        phraseQuery = pattern.sub(' ', str(phraseQuery)).lower()

        return queryList, stemmedQuery, isPhrase, phraseQuery, queryStr, trimmedSearch

    def _removeStopWords(self,wordList):

        stop = set(stopwords.words('english'))
        realWord = [word for word in wordList if word not in stop and len(word) > 2]
        return realWord

    def _porterStemmer(self,wordList):
        return [PorterStemmer().stem(x) for x in wordList]

    def textSearch(self):

        for x, exact in enumerate(self.query):
            tempDict = self._wordSearch(exact, self.stemmedQuery[x])
            sharedPages = self.rankTextResults.keys() & tempDict.keys()
            #print(len(sharedPages))
            #print(len(tempDict))
            for x in sharedPages:
                self.rankTextResults[x] = self.rankTextResults[x] + tempDict[x]
                del tempDict[x]
            #print(len(tempDict))
            #add new urls
            self.rankTextResults.update(tempDict)

    '''in: word,stem
       out: dic[urls] = score'''
    def _wordSearch(self,exact,stem):

        exactDic, stemDic = self._wordLookUp(exact, stem)  # url, positions, imp.
        #print(exactDic)
        #print(stemDic)
        exactScorePages = {}
        for url in exactDic:
            ...
            #print(exactDic[url])
            urlRank, wordPos, imp  = exactDic[url]
            wordCount = len(wordPos)
            #print(urlRank, wordCount, imp)
            exactScorePages[url] = self.computePageScore(urlRank, wordCount, imp, True)
            #print(exactScorePages[url])

        stemScorePages = {}
        for url in stemDic:
            ...
            #print(stemDic[url])
            urlRank, wordPos, imp  = stemDic[url]
            wordCount = len(wordPos)
            #print(urlRank, wordCount, imp)
            stemScorePages[url] = self.computePageScore(urlRank, wordCount, imp, False)
            #print(stemScorePages[url])
        #Score aggregation
        #print(exactScorePages)
        #print(stemScorePages)

        #common pages
        commonPages = exactScorePages.keys() & stemScorePages.keys()
        #print(commonPages)
        wordScoreDict = {**exactScorePages, **stemScorePages}
        for x in commonPages:
            wordScoreDict[x] = exactScorePages[x] + stemScorePages[x]

        return wordScoreDict

    '''returns 2 dicts (exact,stem) in format: dict[url] = [urlRank, [pos], imp]'''
    def _wordLookUp(self,word,stem):
        while True:
            try:
                #exact word
                exactResult = {}
                resultQuery = IndexerTable.select().where(IndexerTable.keyword == word)
                if(resultQuery.exists()):
                    for entry in resultQuery:
                        #print(entry)
                        urlRank = self._getPageRank(entry.url)
                        exactResult.update({entry.url : [urlRank, entry.positions,  entry.importance]})
                break
            except (OperationalError, sqlite3.OperationalError) as e:
                if 'binding' in str(e):
                    print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                    break
                print('QUERY: Database busy, retrying. Exact Word Retrieval')
            except:
                print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                break

        while True:
            try:
                #stem search
                stemResult = {}
                resultQuery = IndexerTable.select().where((IndexerTable.keyword != word) & (IndexerTable.stem == stem))
                if (resultQuery.exists()):
                    for entry in resultQuery:
                        #print(entry)
                        urlRank =  self._getPageRank(entry.url)
                        stemResult.update({entry.url : [urlRank, entry.positions,  entry.importance] })
                break
            except (OperationalError, sqlite3.OperationalError) as e:
                if 'binding' in str(e):
                    print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                    break
                print('QUERY: Database busy, retrying. Stem Word Retrieval')
            except:
                print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                break

        return exactResult,stemResult

    def phraseSearch(self):

        if(self.isPhrase):
            phraseDict = self._phraseLookUp(self.phraseQuery)
        else:
            phraseDict = self._phraseLookUp(self.queryStr)

        for x in phraseDict:
            rank, count, imp = phraseDict[x]
            self.rankPhraseResults[x] = self.computePageScore(rank,count,imp,True, self.isPhrase)

        #print(self.rankPhraseResults)

    '''ret dict[url] = [rank, count, imp]'''
    def _phraseLookUp(self,phrase):

        results = {}
        if(phrase.isalnum()):
            while True:
               try:

                    #print(phrase)
                    resultQuery = FullPages.select().where(FullPages.pageContent.contains(phrase))
                    #print(resultQuery.count())
                    if(resultQuery.exists()):
                        for entry in resultQuery:
                            #print(entry)
                            ...
                            count = entry.pageContent.count(phrase)
                            #print(count)
                            ...
                            urlRank = self._getPageRank(entry.pageURL)
                            results.update({entry.pageURL : [urlRank, count]}) #now add imp
                    break
               except (OperationalError, sqlite3.OperationalError) as e:
                   if 'binding' in str(e):
                       print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                       break
                   print('QUERY: Database busy, retrying. Phrase Retrieval')
               except:
                   print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                   break

            ##more phrase importance in results
            if results:
                #print(results)
                text = phrase.split()
                text = self._removeStopWords(text)
                #print(text)
                if text:
                    #print(text[0])
                    for x in results:
                        #print(x)
                        while True:
                            try:
                                results[x].append(IndexerTable.get((IndexerTable.url == x) & \
                                                                   (IndexerTable.keyword == text[0])).importance)
                                break
                            except (OperationalError, sqlite3.OperationalError) as e:
                                if 'binding' in str(e):
                                    print('QUERY: THIS SHOULD NOT HAPPEN, UNLUCKY!')
                                    break
                                print('QUERY: Database busy, retrying. Phrase Imp')
                            except:
                                print("QUERY: can't find phrase in INDEXER!")
                                break
                else: #all phrase is stop words
                    for x in results:
                        results[x].append(2) #assign this weak phrase with lowest imp
            #print(results) #rank,count,imp
        return results

    def _getPageRank(self,url):
        try:
            return PageRank.get(PageRank.pageURL == url).pageInLinks
        except:
            return 1


    """------------------------------------SCORE FUNCTIONS---------------------------------------------------"""
    def computePageScore(self, urlRank, wordCount, importance, isExact=True, isPhrase=False):
        score = math.log1p(self._frequencyScore(wordCount) * \
                           self._importanceScore(importance) * \
                           self._relevanceScore(isExact) * \
                           self._pagePopularityScore(urlRank)*\
                           self._phraseScore(isPhrase))

        return score

    def _frequencyScore(self, count=1):
        return count * 0.5

    def _importanceScore(self, imp=1):
        if imp == 0:
            return 2.
        elif imp == 1:
            return 1.
        else:
            return .5

    def _relevanceScore(self, isExact=True):  # stem or exact
        if isExact:
            return 2.
        else:
            return 1.
        pass

    def _pagePopularityScore(self, pageVisits=1):
        return pageVisits * 1.

    def _phraseScore(self,isPhrase=False):
        return 3. if isPhrase else 1.


'''###################################OUTSIDERS########################################################################'''
def inputCleanUp(input):
    one = str(input).strip()
    cleanUp = re.compile(r'[\W_]+')
    ans = cleanUp.sub(' ', one).lower()
    #print(ans)
    return ans

def sporterStemmer(content):
    return PorterStemmer().stem(content)

def addSuggestion(content):
    content = inputCleanUp(content)
    #print(content)
    selectQuery = QuerySuggestion.select().where(QuerySuggestion.keyword == content)
    if (selectQuery.exists()):
        QuerySuggestion.update(count = QuerySuggestion.count + 1).where(
            QuerySuggestion.keyword == content).execute()
    else:
        QuerySuggestion.create(keyword = content, stem = sporterStemmer(content)).update()

'''-------------------------------------------INTERFACES------------------------------------------------------------'''

'''CALLED while user is typing the req via AJAX'''
def getSuggestion(typedContent):
    typedContent = inputCleanUp(typedContent)
    #print(typedContent)
    selectQuery = QuerySuggestion.select().where((QuerySuggestion.keyword.contains(typedContent)) |
                                                 QuerySuggestion.stem.contains(sporterStemmer(typedContent))
                                                 ).order_by(-QuerySuggestion.count)

    listy = [x.keyword for x in selectQuery]

    return listy


'''CAllED when user sends req'''
def engineSearch(query):

    res = QuerySearch(query)
    main, related = res.getSearchResult()
    if(main or related):
        addSuggestion(query)



'''..................on typing.....................................'''
typed = 'hel'
print(getSuggestion(typed))

'''..................on request...................................'''
query = 'hello'
engineSearch(query)
