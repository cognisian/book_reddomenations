#!/usr/bin/python3

from Book import Book

import nltk
from nltk.metrics import edit_distance
from nltk.stem.wordnet import WordNetLemmatizer
import enchant

import PIL.Image
import numpy as np
from wordcloud import WordCloud

import MySQLdb

import os
import sys
import random
import json
import re
import unicodedata


spell_dict = enchant.Dict('en_US')


def print_progress(iteration, total, prefix='', suffix='', decimals=1,
                   bar_length=100):
    """ Print a terminal progress bar

    :param iteration: Current iteration
    :type iteration: int
    :param total: Total iterations
    :type total: int
    :param prefix: Prefix string
    :type prefix: str
    :param suffix: Suffix string
    :type suffix: str
    :param decimals: Positive number of decimals in percent complete
    :type decimals: int
    :param bar_length: Character length of bar
    :type bar_length: int
    """
    str_format = "{0:." + str(decimals) + "f}"
    percents = str_format.format(100 * (iteration / float(total)))
    filled_length = int(round(bar_length * iteration / float(total)))
    bar = '█' * filled_length + '-' * (bar_length - filled_length)

    sys.stdout.write('\r%s |%s| %s%s %s' % (
            prefix, bar, percents, '%', suffix)),

    if iteration == total:
        sys.stdout.write('\n')
    sys.stdout.flush()


def slugify(value):
    """
    Converts to lowercase, removes non-word characters (alphanumerics and
    underscores) and converts spaces to hyphens. Also strips leading and
    trailing whitespace.
    """
    value = unicodedata.normalize('NFKD', value).encode(
            'ascii', 'ignore').decode('ascii')
    value = re.sub('[^\w\s-]', '', value).strip().lower()
    return re.sub('[-\s]+', '-', value)


def load_book_from_json(jsonfile):
    """ Parse and create a list of books from JSON

    :param jsonfile: The file to load book data from
    :type jsonfile: str
    :return: The list of :class:`book.Book`s
    :rtype: list
    """
    books = []
    with open(jsonfile, 'r') as db_file:
        data = db_file.read()
        books_raw = json.loads(data)

        for book_raw in books_raw:
            book = Book(**book_raw)
            books.append(book)

    return books


def save_books_to_json(books, jsonfile, indexable=False):
    """ Save a list of books to JSON

    :param books: The list of :class:`book.Book`s
    :type books: list or Book
    :param jsonfile: The file to save book data to.  If books is a list then
    save all books to one file, if books is just a Book then this is a dir
    :type jsonfile: str
    :param indexable: Flag to indicate what structure should be written,
     default is list, if True then write out dict
    :type indexable: bool
    """
    if isinstance(books, list):
        if indexable:
            data = json.dumps(map(lambda book: (book.isbn, book.to_dict()),
                                  books),
                              indent=2)
        else:
            data = json.dumps(list(map(lambda book: book.to_dict(),
                                       books)),
                              indent=2)
    elif isinstance(books, Book):
        str_filename = "{isbn}_{title}.json"
        title = slugify(books.title)
        jsonfile = os.path.join(jsonfile, str_filename.format(isbn=books.isbn,
                                                              title=title))
        data = json.dumps(books.to_dict())

    with open(jsonfile, 'w') as db_file:
        db_file.write(data)


def spellcheck(word):

        result = word
        if not spell_dict.check(word):
            suggestions = spell_dict.suggest(word)
            if suggestions and (edit_distance(word, suggestions[0]) <= 2):
                result = suggestions[0]

        return result


def extract_nomad_data(jsonfile):
    ''' Extract the NomadReader data where data for book is in a single row

    The data returned should refelec the following layout:
     isbn, asin, title, authors, city, country, period, genres, image, summary

     The asin field will need a lookup on Amazon to get its Amazon ID, which is
      ISBN-10.  If book uses ISBN-13 then convert to ISBN-10
     The country will be post processed via comma split or a lookup if no comma
     ie Paris, France versus Paris.

    :return: List of :class:`Book.Book` object to iterate over
    '''

    books = []
    db = MySQLdb.connect(user='schalmers', passwd='Klarn45?',
                         host='127.0.0.1',
                         db='nomad_db_new')

    query = ("""SELECT isbn, title,
            GROUP_CONCAT(IF(parent_term = 'author', term, NULL)) AS author,
            GROUP_CONCAT(IF(parent_term = 'city', term, NULL)) AS city,
            GROUP_CONCAT(IF(parent_term = 'periods', term, NULL)) AS period,
            GROUP_CONCAT(IF(parent_term = 'genres', term, NULL)) AS genres,
            image, summary
            FROM (
                SELECT p.post_title AS 'title', pm.meta_value AS 'isbn',
                LOWER(tp.name) AS 'parent_term', t.name AS 'term',
                pimg.meta_value as image, p.post_excerpt AS summary
                FROM  wp_term_relationships AS tr
                LEFT JOIN wp_posts AS p ON tr.object_id = p.ID
                LEFT JOIN wp_term_taxonomy tt ON
                tr.term_taxonomy_id = tt.term_taxonomy_id
                LEFT JOIN wp_terms AS t ON t.term_id = tt.term_id
                LEFT JOIN wp_postmeta AS pm ON p.ID = pm.post_id
                LEFT JOIN wp_postmeta AS pimg ON p.ID = pimg.post_id
                LEFT JOIN wp_terms AS tp ON tp.term_id = tt.parent
                WHERE p.post_status = 'publish' AND pm.meta_key='isbn_prod' AND
                pm.meta_value!='' AND pimg.meta_key='_nelioefi_url' AND
                tt.parent != 0) AS a
            GROUP BY isbn
    """)

    c = db.cursor()
    c.execute(query)

    books = process_nomad_data(c, jsonfile)

    c.close()
    db.close()

    return books


def process_nomad_data(c, jsonfile):
    ''' Extract the NomadReader book data from the database

    :param c: Cursor to iterate
    :type `MySQLdb.cursors`
    :return: A list of `Book`
    :rtype: List
    '''

    books = []

    i = 0
    itotal = c.rowcount
    print_progress(iteration=i, total=itotal, prefix='Nomad data')
    for row in c:
        if row[0] == '':
            continue

        book = Book(isbn=row[0], title=row[1], image=row[6],
                    summary=row[7])

        book.city = book.split_city_country(row[3])[0]
        book.country = book.split_city_country(row[3])[1]
        book.authors = row[2]
        book.periods = row[4]
        book.genres = row[5]

        book.set_details_amazon()
        book.set_details_geolocation()

        books.append(book)
        save_books_to_json(books, jsonfile)

        i += 1
        print_progress(iteration=i, total=itotal, prefix='Nomad data')

    return books


def extract_book_review_data(book, indexfile):
    ''' Parse Amazon Product Reviews and generate the overal, per review
     sentiment, generate word cloud from reviews

    :param book: The :class:`Book` to index
    :type str:
    :param indexfile: Filename of the searchable index to create
    :type indexfile: str
    '''
    book.set_details_amazon_ratings()


def index_book_data(book, indexfile):
    ''' Add book details to the search index

    :param book: The :class:`Book` to index
    :type str:
    :param indexfile: Filename of the searchable index to create
    :type indexfile: str
    '''
    word_cloud = ''

    stopset = set(nltk.corpus.stopwords.words('english'))
    stopset.update(('book', 'books', 'novel', 'read', 'reader'))

    word_types = ['JJ', 'JJR', 'JJS', 'NN', 'NNS', 'POS',
                  'RB', 'RBR', 'RBS', 'VBD', 'VBG', 'VBN',
                  'VBP', 'VBZ']
    ratings = book.ratings
    if 'reviews' in ratings:

        stemmed_words = []
        for review in ratings['reviews']:
            review_tokens = nltk.word_tokenize(review['review_text'])
            review_tokens = [word for word in review_tokens
                             if (word.isalpha() and
                                 word not in stopset)]
            review_tokens = [(word, wtype)
                             for word, wtype in nltk.pos_tag(review_tokens)
                             if wtype in word_types]

            # ps = nltk.stem.PorterStemmer()
            lemma = WordNetLemmatizer()
            for word, wtype in review_tokens:
                # Skip any words relating to title or author name
                if word.lower() in book.title.lower().split():
                    continue
                if book.authors is not None:
                    for author in book.authors:
                        if word.lower() in author.lower().split():
                            continue

                # Lower case the word and get the root of past-tense verbs
                if wtype.startswith('V'):
                    stemmed_words.append(
                            lemma.lemmatize(spellcheck(word).lower(), pos='v'))
                else:
                    stemmed_words.append(
                            lemma.lemmatize(spellcheck(word).lower()))

            word_cloud = ' '.join(stemmed_words)

    book.word_cloud = word_cloud
    book.where_to_read = random.choice(Book.READ_LOC)
    book.add_to_index(indexfile)


def extract_book_wordcloud(book, wordclouddir):
    ''' Create word cloud image from reviews retrieved from Amazon

    :param book: The :class:`Book` to generate word clud image
    :type str:
    :param wordclouddir: Dirname of the word cloud images
    :type wordclouddir: str
    '''
    words = nltk.word_tokenize(book.word_cloud)
    fd = nltk.FreqDist(words)

    mask_file = ''
    if (book.where_to_read[0] is not None and book.where_to_read[0] != '' and
            words != '' and len(words) > 0):

        mask_type = book.where_to_read[0].lower().replace(' ', '_')
        mask_filename = '{}.png'.format(mask_type)
        mask_dir = os.path.dirname(wordclouddir)
        mask_file = os.path.join(mask_dir, 'src', mask_filename)

        mask_img = PIL.Image.open(mask_file)
        mask = np.array(mask_img)

        wc = WordCloud(font_path='/usr/share/fonts/droid/DroidSans.ttf',
                       background_color="white", mask=mask,
                       max_words=1000, max_font_size=400,
                       random_state=42)

        # generate word cloud
        wc.generate_from_frequencies(fd)
        # wc.recolor(color_func=image_colors)
        wc_img_file = '{}.png'
        wc.to_file(os.path.join(wordclouddir,
                                wc_img_file.format(slugify(book.title))))
        #
        # import matplotlib.pyplot as plt
        # plt.axis("off")
        # plt.imshow(wc, interpolation='bilinear')
        #
        # plt.figure()
        # # plt.imshow(mask, cmap=plt.cm.gray, interpolation='bilinear')
        # plt.axis("off")
        # plt.imshow(mask, interpolation='bilinear')
        #
        # plt.show()


def resize_book_covers(book, imagedir):
    ''' Resize the covers retrieved from Amazon to standard size

    :param book: The :class:`Book` to resize book cover image
    :type str:
    :param imagedir: Dirname of the resized book cover images to create
    :type imagedir: str
    '''
    pass


def main(action, jsonfile, indexfile, wordclouddir, imagedir, splitdir):
    """ Main entry point to begin processing the NomadReader data.

    :param action: The action to take for processing.  One of: [
        init, extract, all]
    :type action: str
    :param jsonfile: Filename of the the CSV file to read or write
    :type jsonfile: str
    :param indexfile: Dirname of the searchable index to create
    :type indexfile: str
    :param wordclouddir: Dirname of the word cloud images to create
    :type wordclouddir: str
    :param imagedir: Dirname of the resized book cover images to create
    :type imagedir: str
    :param splitdir: Dirname in which to generate individual JSON book files
    :type splitdir: str
    """

    books = []
    if action == 'all' or action == 'init':
        books = extract_nomad_data(jsonfile)
        save_books_to_json(books, jsonfile)

    if action == 'all' or action == 'extract':
        if books is None or len(books) == 0:
            books = load_book_from_json(jsonfile)

        i = 1
        itotal = len(books)
        for book in books:
            extract_book_review_data(book)
            print_progress(iteration=i, total=itotal, prefix='Review data')
            i += 1

        save_books_to_json(books, jsonfile)

    if action == 'all' or action == 'index':
        if books is None or len(books) == 0:
            books = load_book_from_json(jsonfile)

        i = 1
        itotal = len(books)
        for book in books:
            index_book_data(book, indexfile)
            print_progress(iteration=i, total=itotal, prefix='Index data')
            i += 1

        save_books_to_json(books, jsonfile)

    if action == 'all' or action == 'wordcloud':
        if books is None or len(books) == 0:
            books = load_book_from_json(jsonfile)

        i = 1
        itotal = len(books)
        for book in books:
            extract_book_wordcloud(book, wordcloudname)
            print_progress(iteration=i, total=itotal, prefix='Word Cloud')
            i += 1

    if action == 'all' or action == 'resize':
        if books is None or len(books) == 0:
            books = load_book_from_json(jsonfile)

        i = 1
        itotal = len(books)
        for book in books:
            resize_book_covers(book, imagedir)
            print_progress(iteration=i, total=itotal, prefix='Resize')
            i += 1

    if action == 'all' or action == 'split':
        if books is None or len(books) == 0:
            books = load_book_from_json(jsonfile)

        i = 1
        itotal = len(books)
        for book in books:
            save_books_to_json(book, splitdir)
            print_progress(iteration=i, total=itotal, prefix='Split')
            i += 1


if __name__ == '__main__':
    import argparse as arg

    default_index = os.getcwd() + "/index/nomadreader.idx"
    default_wordcloud_imgs = os.getcwd() + "/images/wordcloud"
    default_image = os.getcwd() + "/images/covers"
    default_json = os.getcwd() + "/nomad_db.json"
    default_split = os.getcwd() + "/content"

    parser = arg.ArgumentParser(description="""Process the NomadReader database
                                and create a CSV dump.  Using the ISBN number
                                get summary and rating from Amazon.  And if
                                specified create a searchable index""")
    parser.add_argument('cmd', choices=['init', 'extract', 'index',
                                        'wordcloud', 'resize', 'split', 'all'],
                        nargs='?', default='all',
                        help="""The operation to perform""")
    parser.add_argument('-f', '--file', dest='filename', required=False,
                        default=default_json, help="""The JSON file to dump
                        and load Book data""")
    parser.add_argument('-i', '--index', dest='indexname',
                        default=default_index, required=False,
                        help="""The searchable index to create""")
    parser.add_argument('-w', '--wordcloud', dest='wordcloudname',
                        default=default_wordcloud_imgs, required=False,
                        help="""The directory to generate word cloud images""")
    parser.add_argument('-r', '--resize', dest='imagename',
                        default=default_image, required=False,
                        help="""The directory to generate resized book cover
                        images""")
    parser.add_argument('-s', '--split', dest='splitname',
                        default=default_split, required=False,
                        help="""The directory to split JSON into individual
                         book JSON files into""")

    args = parser.parse_args()

    # Expand any ~ and relative dir names
    filename = os.path.expanduser(args.filename)
    filename = os.path.realpath(filename)

    indexname = os.path.expanduser(args.indexname)
    indexname = os.path.realpath(indexname)

    wordcloudname = os.path.expanduser(args.wordcloudname)
    wordcloudname = os.path.realpath(wordcloudname)

    imagename = os.path.expanduser(args.imagename)
    iimagename = os.path.realpath(imagename)

    splitname = os.path.expanduser(args.splitname)
    splitname = os.path.realpath(splitname)

    # Run Forest, run!
    main(args.cmd, filename, indexname, wordcloudname, imagename, splitname)
