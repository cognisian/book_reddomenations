import os
import html
import time
import random
import io

from PIL import Image
import pytesseract as tess
# import http.client as http_client

from whoosh import index as idx
from whoosh.fields import Schema, ID, TEXT, KEYWORD, NUMERIC

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

import bottlenose as bn
from urllib.error import HTTPError
from bs4 import BeautifulSoup
import requests as req

import nltk


# http_client.HTTPConnection.debuglevel = 1


class Book(object):

    WORDS_PAGE = 250

    _CITY_CACHE = dict()
    # Initially populate some difficult to get geolocations due to numbers
    # of results returned or hard to gues countries
    _CITY_CACHE['London'] = ('England', 51.50853, -0.12574)
    _CITY_CACHE['Jerusalem'] = ('Israel', 31.75, 35.00)

    STORY_ARCS = [('Rags_To_Riches', 'The story gets better over time'),
                  ('Person_In_A_Hole', """Fortunes fall, but the protagonist
                    bounces back"""),
                  ('Cinderella', """An initial rise in good fortunes, followed
                    by a setback, but a happy ending"""),
                  ('Tragedy', "Things only get worse"),
                  ('Oedipus', """Bad luck, followed by promise, ending in a
                    final fall"""),
                  ('Icarus', "Opens with good fortunes, but doomed to fail")
                  ]

    READ_LOC = [('Beach', 'IS there any better place to read'),
                ('Plane', """Locked in a metal tube and cart service
                 stopped"""),
                ('Commuter Train', """Hi ho, hi ho, its off to work we go"""),
                ('Inter City Train', "Choo-choo!!!"),
                ('Commuter Bus', """Stand And Read!"""),
                ('Inter City Bus', "This is gonna be a long ride"),
                ('Cafe', "Damn, my beret blew away"),
                ('Park', "Leaves of grass are all up in my stuff"),
                ]

    def __init__(self, isbn='', asin='', title='', rank=0, authors=None,
                 city='', country='', latitude=0.0, longitude=0.0,
                 periods=None, genres=None, image='', ratings=None,
                 readability=0, story_arc=None, where_to_read=None,
                 word_cloud='', summary=''):
        """ Constructor

        :param isbn: The ISBN of this book
        :type isbn: string
        :param asin: The ASIN of this book
        :type asin: string
        :param title: The title of this book
        :type title: string
        :param rank: The Amazon sales rank
        :type rank: int
        :param authors: The authors of the book. This can be passed as a lists
            or a comma separated string in author[, author, author]
        :type authors: list or string
         format separated by spaces
        :param city: The city this book is associated with.  T
        :type city: string
        :param country: The country this book is associated with
        :type country: string
        :param lat: The latitude of the city
        :type lat: float
        :param longt: The longtitude of the city
        :type long: float
        :param periods: The time periods of the book.  This can be passed as a
            list or a comma separated string in period[, period, period]
        :type periods: list or string
        :param genres: The genres of the book.  This can be passed as a
            list or a comma separated string in genre[, genre, genre]
        :type genres: list or string
        :param image: The Amazon image URL
        :type image: string
        :param ratings: The Amazon ratings data
        :type ratings: dict
        :param readability: The readability score of book, currently based on:
            page count * avg words per page (250)
        :type readability: dict
        :param story_arc: What type of story is it
        :type story_arc: tuple
        :param where_to_read: A good place to read the book
        :type where_to_read: string
        :param word_cloud: Set of relevant words used by reviewers
        :type word_cloud: string
        :param summary: The summary of the book
        :type summary: string
        """

        self.isbn = isbn

        self.asin = asin
        self.title = title
        self.rank = rank
        self._authors = authors
        self.city = city
        self.country = country
        self.latitude = latitude
        self.longitude = longitude
        self._periods = periods
        self._genres = genres
        self.image = image
        self.ratings = ratings
        self.readability = 0
        # self.story_arc = story_arc
        self.story_arc = random.choice(Book.STORY_ARCS)
        self.where_to_read = where_to_read
        self.word_cloud = word_cloud
        self.summary = summary

        self._response = None

        self._amzn = bn.Amazon('AKIAINMQATUGYM2WDFLA',
                               'GASZGld3IDt6Ui4pYAzWDQyKko+YSxVFA+RSd171',
                               'nomadus-20',
                               MaxQPS=0.9, Parser=self._parse_amazon_xml)

    def get_index_schema(self):
        """ Returns the indexing schema

        :return: The schema to use for indexing
        :rtype: :class:`whoosh.Schema`
        """
        return Schema(isbn=ID(unique=True,
                              stored=True),
                      title=TEXT,
                      authors=KEYWORD(lowercase=True,
                                      scorable=True,
                                      commas=True),
                      rank=NUMERIC,
                      city=KEYWORD(lowercase=True,
                                   scorable=True),
                      country=KEYWORD(lowercase=True,
                                      scorable=True),
                      periods=KEYWORD(lowercase=True,
                                      scorable=True,
                                      commas=True),
                      genres=KEYWORD(lowercase=True,
                                     scorable=True,
                                     commas=True),
                      ratings=TEXT,
                      readability=NUMERIC,
                      story_arc=KEYWORD(lowercase=True,
                                        scorable=True),
                      where_to_read=KEYWORD(lowercase=True,
                                            scorable=True),
                      word_cloud=TEXT,
                      summary=TEXT)

    def to_dict(self, indexable=False):
        """ Returns this book as a dict

        :return: This book as a dictionary
        :rtype: Dict
        """
        result = {}

        temp = [(col, getattr(self, col)) for col in self._get_fieldnames()]
        result = dict((k, v) for k, v in temp)

        if indexable:
            result = dict(result['isbn'], result)

        return result

    def set_details_amazon(self):
        """ Using ISBN lookup book details from Amazon Prodict API and set Book
        properties accordingly
        """
        if self.isbn is not None and self.isbn != '':

            result_groups = "Medium,SalesRank,Reviews"
            retry = 3
            success = False
            while not success:
                try:
                    self._response = self._amzn.ItemLookup(
                            ItemId=self.isbn, ResponseGroup=result_groups,
                            SearchIndex="Books", IdType="ISBN")
                    retry = 0
                    success = True
                except HTTPError:
                    retry -= 1
                    time.sleep(1)

            if success:
                self.asin = self._get_amazon_item_value('ASIN')
                self.image = self._get_amazon_item_value('LargeImage.URL')

                # Could use publisher default here to calculate words/book
                # instead of just an average
                temp = self._get_amazon_item_value(
                        'ItemAttributes.NumberOfPages')
                if temp is not None and temp != '':
                    self.readability = int(temp) * Book.WORDS_PAGE

                temp = self._get_amazon_item_value('SalesRank')
                if temp is not None and temp != '':
                    self.rank = int(temp)

                if self.summary == '':
                    self.summary = (self._get_amazon_item_value(
                            'EditorialReviews.EditorialReview.Content'))

    def set_details_amazon_ratings(self, pages=1):
        """ Using ISBN lookup book reviews from the main Amazon URL and not the
         Product API due to captchas on the reviews URL provided by Product API

        :param pages: The number of pages of reviews to go through
        :type pages: int
        """
        if self.isbn is not None and self.isbn != '':

            if self.ratings is None:
                self.ratings = {}

            for page in self._load_amazon_review_pages(pages):

                rating_root = page.select(
                        "div#cm_cr-product_info "
                        "div.reviewNumericalSummary "
                )

                if rating_root is not None and len(rating_root) == 1:

                    rating_score = rating_root[0].find(
                            "span", class_="arp-rating-out-of-text")

                    if rating_score is not None:
                        score = rating_score.text.split(' ')[0]
                        self.ratings['rating'] = float(score)

                    total_reviews = rating_root[0].find(
                            "span", class_="totalReviewCount")

                    if total_reviews is not None:
                        self.ratings['num_ratings'] = (
                                int(total_reviews.text.replace(',', '')))

                # Extract the review text for analysis
                reviews_root = page.select(
                        "div#cm_cr-review_list > div.review")

                if reviews_root is not None and len(reviews_root) >= 1:

                    reviews = []
                    for review in reviews_root:
                        review_details_rows = review.select("div.a-row")

                        detail_sentiment = review_details_rows[0].find(
                                'a', {'class': 'a-link-normal'})
                        detail_sentiment_score = detail_sentiment.text
                        detail_sentiment_score = float(
                                detail_sentiment_score.split(' ')[0])

                        review_words = review_details_rows[3].find(
                                'span', {'class': 'review-text'})
                        reviews.append({
                                'review_sentiment': detail_sentiment_score,
                                'review_text': review_words.text
                        })

                    self.ratings['reviews'] = reviews

                    # Transform review text to word cloud
                    word_cloud = ''

                    remove_types = ['DET', 'CNJ']
                    for review in reviews['reviews']:
                        review_tokens = nltk.pos_tag(
                                nltk.word_tokenize(review['review_text']))
                        filtered_words = [word for word, wtype in review_tokens
                                          if wtype not in remove_types]
                        word_cloud += filtered_words

                    self.word_cloud = word_cloud

    def set_details_geolocation(self):
        """ Usig values from City/Country lookup the full city, country and
         lat/lon values and update Book properties accordingly
        """

        if self.city in Book._CITY_CACHE:
            temp = Book._CITY_CACHE[self.city]
            self.country = temp[0]  # Country
            self.latitude = temp[1]  # Lat
            self.longitude = temp[2]  # Long
        else:
            loc = Nominatim()
            try:
                country = loc.geocode({
                        'city': self.city, 'country': self.country},
                        exactly_one=False, addressdetails=True,
                        language='en')

                if country is not None:
                    for location in country:
                        if (location.raw['type'] == 'city' and
                                'country' in location.raw['address']):

                            self.country = location.raw['address']['country']
                            self.latitude = float(location.raw['lat'])  # Lat
                            self.longitude = float(location.raw['lon'])  # Long

                            # Cache results
                            Book._CITY_CACHE[self.city] = (
                                    location.raw['address']['country'],
                                    float(location.raw['lat']),
                                    float(location.raw['lon'])
                            )
                            break

            except (GeocoderTimedOut, GeocoderServiceError) as ex:
                print("Skipped " + self.title)

    def split_city_country(self, value):
        """ Given a string in form of `city[, country]` split into parts

        :return: The separate city and country
        :rtype: tuple
        """
        city = ''
        country = ''
        if value is not None:
            value_split = value.split(',')
            if len(value_split) >= 1:
                city = value_split[0].strip()
                if len(value_split) == 2:
                    # City provided a countryas well
                    country = value_split[1].strip()

        return (city, country)

    def add_to_index(self, indexfile, overwrite=False):
        ''' Adds this book to searchable index, creating the index if necessary

        :param indexfile: Filename of the searchable index to create/update
        :type indexfile: str
        :param overwrite: Flag indicating that the index should overwrite a
         previous instance
        :type indexfile: bool
        '''
        if not os.path.exists(indexfile):
            os.mkdir(indexfile)

        search = None
        if overwrite or not idx.exists_in(indexfile):
            search = idx.create_in(indexfile, self.get_index_schema())
        else:
            search = idx.open_dir(indexfile)

        with search.writer() as update:
            # Error in getting rank so have to work around bug
            if self.rank == '':
                self.rank = 0

            # Convert lists to comma separated values
            authors = ''
            if self.authors is not None:
                authors = ",".join(self.authors)

            periods = ''
            if self.periods is not None:
                periods = ",".join(self.periods)

            genres = ''
            if self.genres is not None:
                genres = ",".join(self.genres)

            # Convert ratings dict to word cloud by storing the top
            # most frequent words
            ratings = ''
            if self.ratings is not None and 'reviews' in self.ratings:
                ratings = " ".join(review['review_text']
                                   for review in self.ratings['reviews'])

            # Convert story arc tuple to phrase searching
            story_arc = self.story_arc[0] + " " + self.story_arc[1]

            update.add_document(isbn=self.isbn, title=self.title,
                                rank=self.rank, city=self.city,
                                country=self.country,
                                authors=authors, periods=periods,
                                genres=genres, ratings=ratings,
                                readability=self.readability,
                                story_arc=story_arc,
                                where_to_read=self.where_to_read,
                                summary=self.summary)

    @property
    def authors(self):
        return self._authors

    @authors.setter
    def authors(self, value):
        """ Setter to parse string in form of `author1[, author2, ...]`
        """
        if value is not None:
            if isinstance(value, str):
                if self._authors is None:
                    self._authors = []
                value_split = value.split(',')
                if len(value_split) >= 1:
                    for author in value_split:
                        self._authors.append(author.strip())
            else:
                self._authors = value

    @property
    def periods(self):
        return self._periods

    @periods.setter
    def periods(self, value):
        """ Setter to parse string in form of `period1[, period2, ...]`
        """
        if value is not None:
            if isinstance(value, str):
                if self._periods is None:
                    self._periods = []
                value_split = value.split(',')
                if len(value_split) >= 1:
                    for period in value_split:
                        self._periods.append(period.strip())
            else:
                self._periods = value

    @property
    def genres(self):
        return self._genres

    @genres.setter
    def genres(self, value):
        """ Setter to parse string in form of `genre1[, genre2, ...]`
        """
        if value is not None:
            if isinstance(value, str):
                if self._genres is None:
                    self._genres = []
                value = html.unescape(value)
                value_split = value.split(',')
                if len(value_split) >= 1:
                    for genre in value_split:
                        self._genres.append(genre.strip())
            else:
                self._genres = value

    def _get_fieldnames(self):
        """ Returns the list of fields suitable for writing

        :return: The list of fieldnames
        :rtype: List of strings
        """
        ignore_fields = ['_amzn', '_response']
        cols = []
        for col in self.__dict__:
            if col not in ignore_fields:
                if col.startswith('_', 0, 1):
                    col = col[1:]

                cols.append(col)

        return cols

    def _parse_amazon_xml(self, text):
        """ Parse the results returned from Amazon

        :param text: XML result from Amazon
        :type text: string
        :return: The Amazon result XML as an object
        :rtype: :class:`BeautifulSoup`
        """
        return BeautifulSoup(text, 'xml')

    def _get_amazon_item_value(self, find_tag):
        """ Get the value specified in `field` from Amazon ItemLookup response

        :param field: The field name, relative to Items.Item
        :type field: String
        :return: The text value of the requested field or None if no field
        :rtype: String or None
        """
        result = ''
        if (self._response is not None and
                getattr(self._response.Items, 'Errors') is None):

            if (getattr(self._response, 'Items') is not None and
                    getattr(self._response.Items, 'Item') is not None and
                    self._response.Items.Item is not None):

                item = self._response.Items.Item
                # Given field name which could be in dotted notation, replace
                # dot with parent child relation for tag finding in XML
                if item is not None:
                    find_selector = find_tag.replace('.', ' > ')
                    tags = item.select(find_selector)
                    if tags is not None and len(tags) != 0:
                        try:
                            if getattr(tags[0], 'text') is not None:
                                result = tags[0].text
                        except AttributeError:
                            print('AttributeError on item.text' + tags[0])

        return result

    def _load_amazon_review_pages(self, pages=1):
        """ Fetch and parse the Amazon reviews URL

        :param pages: The number of Amazon review URL to navigate
        :type pages: int (default: 1)
        :return: An iterator over the full review pages
        :rtype: iter
        """
        desktop_agents = [
                "Mozilla/5.0 (Windows NT 6.1; WOW64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.99 Safari/537.36",

                "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.99 Safari/537.36",

                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.99 Safari/537.36",

                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) "
                "AppleWebKit/602.2.14 (KHTML, like Gecko) "
                "Version/10.0.1 Safari/602.2.14",

                "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.71 Safari/537.36",

                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.98 Safari/537.36",

                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.98 Safari/537.36",

                "Mozilla/5.0 (Windows NT 6.1; WOW64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.71 Safari/537.36",

                "Mozilla/5.0 (Windows NT 6.1; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/54.0.2840.99 Safari/537.36",

                "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:50.0) "
                "Gecko/20100101 Firefox/50.0"
        ]

        prev_page = 1
        page = 1

        amzn_referer_url = "https://www.amazon.com/product-reviews/" \
            "{}?ie=UTF8&showViewpoints=0&pageNumber={}&" \
            "sortBy=bySubmissionDateDescending"
        amzn_url = "https://www.amazon.com/product-reviews/" \
            "{}?ie=UTF8&showViewpoints=0&pageNumber={}&" \
            "sortBy=bySubmissionDateDescending"

        while page <= pages:
            url = amzn_url.format(self.isbn, page)
            ref_url = amzn_referer_url.format(self.isbn, prev_page)

            headers = {'User-Agent': random.choice(desktop_agents),
                       'Referer': ref_url,
                       'Accept': "text/html,application/xhtml+xml,"
                       "application/xml;q=0.9,image/webp,*/*;q=0.8"
                       }

            # response = req.get(url, headers=headers, proxies=proxies)
            response = req.get(url, headers=headers)
            if (response.status_code >= 200 and response.status_code < 400):

                reviews_html = BeautifulSoup(response.text, 'html.parser')

                done = False
                while not done:

                    cookies = response.cookies

                    # Determine if we have a captcha
                    captcha_root = reviews_html.select(
                            "div.a-section form "
                    )
                    if captcha_root is not None and len(captcha_root) == 1:

                        # Get the captcha img
                        captcha_img = captcha_root[0].select(
                                "div.a-text-center img")

                        if captcha_img is not None and len(captcha_img) == 1:

                            img_src = (captcha_img[0])['src']
                            resp = req.get(img_src, headers=headers)
                            if (resp.status_code >= 200 and
                                    resp.status_code <= 400):

                                img_data = resp.content
                                stream = io.BytesIO(img_data)
                                captcha = Image.open(stream)

                                text = tess.image_to_string(captcha).strip()

                                captcha_url_form = 'https://www.amazon.com{}'
                                captcha_url = captcha_url_form.format(
                                    (captcha_root[0])['action']
                                )

                                amzn_hidden = captcha_root[0].select("input")
                                amzn_token = ''
                                amzn_r_token = ''
                                for inputs in amzn_hidden:
                                    if inputs['name'] == 'amzn':
                                        amzn_token = inputs['value']
                                    if inputs['name'] == 'amzn-r':
                                        amzn_r_token = inputs['value']

                                params = {
                                    'field-keywords': text.lower(),
                                    'amzn': amzn_token,
                                    'amzn_r': amzn_r_token
                                }

                                time.sleep(0.5)
                                response = req.get(
                                        captcha_url,
                                        headers=headers,
                                        params=params,
                                        allow_redirects=False)
                                reviews_html = BeautifulSoup(response.text,
                                                             'html.parser')
                    else:
                        done = True
                        response = req.get(url, headers=headers,
                                           cookies=cookies)
                        if (response.status_code >= 200 and
                                response.status_code < 400):
                            reviews_html = BeautifulSoup(response.text,
                                                         'html.parser')

                    yield reviews_html

            prev_page = page
            page += 1
