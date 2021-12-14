import argparse as arg
import re
import string
import csv
import time
import os

import requests
import wikitextparser as wp

from nomadschema import NomadSchema
from whoosh import index as idx
import nltk

from pprint import pprint


def create_wiki_name_slug(name, skip_middle=False):
    """ Create a wiki slug for name dict

    Given a name dict create wiki slug string, with url encoded characters
     {'first': 'J.'', 'middle':'R. R.', 'last':'Tolkien'} -> J._R._R._Tolkien
     {'first': 'Jean'', 'middle':'le Rond', 'last':'D'Alembert'} ->
                                                   Jean_le_Rond_d%27Alembert

    @param name: The name to convert
    @type name: dict
    @param skip_middle: If the name dict contains key 'middle', then ignore it
    when building the wiki slug
    @return: Return the constructed wiki slug
    @rtype: str
    """
    slug = name['first'] + '_'
    if not skip_middle and 'middle' in name and name['middle']:
        slug += name['middle'].replace(' ', '_') + '_'
    slug += name['last']

    return slug


def create_wiki_title_slug(title):
    """ Extract the book title parts from the string#

    Given a title dict create the wiki slug, with url encoded characters
    Given: {title: 'The Castle'} -> wiki slug The_Castle
    Given: Something Comes (Ballentine Book) -> Something_Comes
    Given: Flood : Mississippi 1927 -> Flood%3A_Mississippi_1927

    @param title: The book title to convert
    @type title: str
    @return: Return the constructed wiki slug
    @rtype: str
    """
    slug = title['title']
    if 'subtitle' in title and title['subtitle']:
        slug += '%3A_' + title['subtitle']

    return slug.replace(' ', '_')


def extract_name_parts(name):
    """ Extract a string into name parts: last, first, middle name/initals

    Given a full name in in a string extract the different name parts and
    create # the Wikipedia slug representation of the name:
    Given name: A. A. Milne -> first: A., middle:A., last:Milne
    Given name: J.R.R. Tolkien -> first: J., middle:R. R., last:Tolkiendict
    Given name: Bret Easton Ellis -> first:Bret, middle:Easton, last:Ellis

    @param name: The author name to split into name parts
    @type nammme: str
    @return: The name parts
    @rtype: dict
    """
    parsed_name = {}

    # Count the number of spaces to determine how many "words" a name
    name_parts = name.split(' ')
    name_part_count = len(name_parts)

    # Parse the name into name parts based on space separated words
    parsed_name['last'] = name_parts[-1].capitalize()
    parsed_name['first'] = name_parts[0].capitalize()
    parsed_name['middle'] = ''

    # However there could be cases where initials/periods occur or middle
    # names and further splitting of first name may be required
    if name_part_count == 2:
        # Check if first part is a set of initials, which have no space char
        # separating different initials
        initials_parts = name_parts[0].split('.')
        if len(initials_parts) > 1:
            parsed_name['first'] = initials_parts[0].capitalize() + '.'
            parsed_name['middle'] = ". ".join(
                initials_parts[1:]).strip().upper()

    elif name_part_count > 2 and name_part_count <= 4:
        # Last word is surname, first word is first name and the rest are
        # middle names
        parsed_name['middle'] = "".join(
                name_parts[1:-1]).capitalize()

    return parsed_name


def extract_title_parts(title):
    """ Extract the book title

    Given a book title, extract the title parts, title and subtitle if any
    colons and finally remove any parenthesis
    Given name: A Second Chicken Soup for the Woman's Soul (Chicken Soup for
    the Soul Series) -> A Second Chicken Soup for the Woman's Soul
    Given name: Flood : Mississippi 1927 -> title: Flood,
                                         subtitle: Mississippi 1927

    @param title: The book title to split into parts
    @type title: str
    @return: The title parts
    @rtype: dict
    """

    parsed_title = {}

    # Check for paraenthesis and strip out everything after
    parenthesis = title.find('(')
    if parenthesis != -1:
        title = title[0:parenthesis].strip()

    title_parts = title.split(':')
    parsed_title['title'] = string.capwords(title_parts[0].strip())
    parsed_title['subtitle'] = ''
    if len(title_parts) == 2:
        parsed_title['subtitle'] = string.capwords(title_parts[1].strip())

    return parsed_title


def get_book_infoblock_plot(title):
    """ Query the Wikipedia API to get the infoblock and Plot sections for a book

    @param title:  The book title to query Wikipedia with
    @type title: str
    @return: Return the info extracted from Infobox
    @rtype: dict
    """
    result = {}

    endpoint = 'https://en.wikipedia.org/w/api.php'
    headers = {
        'Api-User-Agent': 'BookInfoGetter/1.0 (superintendent.sean@gmail.com)'
    }
    payload = {
        'format': 'json',
        'formatversion': 2,
        'action': 'query',
        'prop': 'revisions',
        'rvprop': 'content',
        'titles': create_wiki_title_slug(title)
    }
    r = requests.get(endpoint, headers=headers, params=payload)
    info = r.json()

    # If we have one result, we matched exactly
    if ('pageid' in info['query']['pages'][0] and
            len(info['query']['pages']) == 1):

        wiki_id = info['query']['pages'][0]['pageid']
        result['wiki_id'] = wiki_id

        # Extract Infoblock information, contained in the first section
        content = info['query']['pages'][0]['revisions'][0]['content']
        wiki_text = wp.parse(content)

        section = wiki_text.sections[0]
        infobox = [template for template in section.templates
                   if template.name.startswith('Infobox')]
        if infobox[0].has_arg('country'):
            result['country'] = infobox[0].get_arg('country').value.strip()
        if infobox[0].has_arg('genre'):
            result['genres'] = []
            if len(infobox[0].get_arg('genre').wikilinks) >= 1:
                for link in infobox[0].get_arg('genre').wikilinks:
                    result['genres'].append(link.target)
            else:
                result['genres'] = list(
                        infobox[0].get_arg('genre').value.strip())
        if infobox[0].has_arg('release_date'):
            reldate = infobox[0].get_arg('release_date').value.strip()
            result['pubdate'] = time.strptime(reldate, "%d %B %Y")

        # Extract Plot information, contained in the Plot section
        plot_section = [section for section in wiki_text.sections
                        if section.title.startswith('Plot')]
        if len(plot_section) == 1:
            # Remove the wikilinks formatting from contents
            for link in plot_section[0].wikilinks:
                orig_target = link.target
                orig_text = link.text

                # If the target part of the wikilink contains any (,),-,# then
                # set the wikilink target to the text part of wikilink and
                # set # text to empty, else use the target text and set text
                # to empty.
                # This is so we get a the full name without silly chars
                # ie disassemble the wikilink structure and replace with a
                # string that looks like a name/noun
                if any(x in orig_target for x in ['(', ')', '-', '#']):
                    if orig_text is not None:
                        link.target = orig_text
                        link.text = None
                    else:
                        link.text = None
                else:
                    link.text = None

            # Remove wikilinks formatting [[ ]] from contents and replace
            # with plain text
            contents = plot_section[0].contents
            contents = re.sub(r"\[\[([\w\s']+)\]\]", r'\1', contents)
            result['content'] = contents

    return result


def extract_entity_names(t):
    """ Extract entity names from parsed NLTK

    @param t: The current node of NLTK tree
    @type object
    @return: List of extracted entity names
    @rtype: list
    """
    entity_names = []

    if hasattr(t, 'label') and t.label:
        if t.label() == 'NE':
            entity_names.append(' '.join([child[0] for child in t]))
        else:
            for child in t:
                entity_names.extend(extract_entity_names(child))

    # from nltk.sem import relextract
    # pairs = relextract.tree2semi_rel(tree)
    # for s, tree in pairs[18:22]:
    #     print('("...%s", %s)' % (" ".join(s[-5:]),tree))

    # reldicts = relextract.semi_rel2reldict(pairs)
    # for k, v in sorted(reldicts[0].items()):
    #     print(k, '=>', v) # doctest: +ELLIPSIS

    # import re
    # IN = re.compile(r'.*\bin\b(?!\b.+ing\b)')
    # for fileid in ieer.fileids():
    # for doc in ieer.parsed_docs(fileid):
    #     for rel in relextract.extract_rels('ORG', 'LOC', doc, corpus='ieer',
    #                                        pattern = IN):
    # print(relextract.rtuple(rel))  # doctest: +ELLIPSIS

    # de = """
    # ... .*
    # ... (
    # ... de/SP|
    # ... del/SP
    # ... )
    # ... """
    # DE = re.compile(de, re.VERBOSE)
    # rels = [rel for doc in conll2002.chunked_sents('esp.train')
    #     for rel in relextract.extract_rels('ORG', 'LOC', doc,
    #                                       corpus='conll2002', pattern = DE)]
    # for r in rels[:10]:
    #   print(relextract.clause(r, relsym='DE'))

    return entity_names


def extract_named_entities(text):
    """ Parse a string with NLTK and extract named entities

    @param text:  The text to do named entity recognition on
    @type text: string
    @return: The list of named entities
    @rtype: list
    """
    sentences = nltk.sent_tokenize(text)
    tokenized_sentences = [nltk.word_tokenize(sentence)
                           for sentence in sentences]
    tagged_sentences = [nltk.pos_tag(sentence)
                        for sentence in tokenized_sentences]
    chunked_sentences = [nltk.ne_chunk(sentence, binary=False)
                         for sentence in tagged_sentences]

    entity_names = []
    for tree in chunked_sentences:
        # Print results per sentence
        # print extract_entity_names(tree)
        # entity_names.extend(extract_entity_names(tree))

        pprint(tree)

    return entity_names


def _calculate_languages_ratios(text):
    """
    Calculate probability of given text to be written in several languages and
    return a dictionary that looks like:
    {'french': 2, 'spanish': 4, 'english': 0}

    @param text: Text whose language want to be detected
    @type text: str
    @return: Dictionary with languages and unique stopwords seen in analyzed
     text
    @rtype: dict
    """

    languages_ratios = {}

    '''
    nltk.wordpunct_tokenize() splits all punctuations into separate tokens
    >>> wordpunct_tokenize("That's thirty minutes away. I'll be there in ten.")
    ['That', "'", 's', 'thirty', 'minutes', 'away', '.', 'I', "'", 'll', 'be',
     'there', 'in', 'ten', '.']
    '''

    tokens = nltk.wordpunct_tokenize(text)
    words = [word.lower() for word in tokens]

    # Compute per language included in nltk number of unique stopwords
    # appearing in analyzed text
    for language in nltk.corpus.stopwords.fileids():
        stopwords_set = set(nltk.corpus.stopwords.words(language))
        words_set = set(words)
        common_elements = words_set.intersection(stopwords_set)

        languages_ratios[language] = len(common_elements)

    return languages_ratios


def detect_language(str):
    """ Detect the language used

    @param str: The text to determine the language of
    @type: str
    @return: The spoken language name
    @rtype: str
    """

    ratios = _calculate_languages_ratios(str)
    most_rated_language = max(ratios, key=ratios.get)
    print(most_rated_language)

    return most_rated_language


def main(filename, indexname):
    """ Process the CSV file and do a lookup on Wikipedia

    Process the CSV file and do a lookup on Wikipedia for book title and gather
    # the Infoblock section to extract Genre information as well as the Plot
    # section to see if there is some GeoLocation references via NLTK
    """
    # Create the index
    schema = NomadSchema()

    indexname = os.path.expanduser(indexname)
    indexname = os.path.realpath(indexname)
    if not os.path.exists(indexname):
        os.mkdir(indexname)
        nr_idx = idx.create_in(indexname, schema=schema,
                               indexname="nomadreader")
    else:
        nr_idx = idx.open_dir(indexname, schema=schema,
                              indexname="nomadreader")

    writer = nr_idx.writer()

    # Parse out the author and isbn and book title
    filename = os.path.expanduser(filename)
    filename = os.path.realpath(filename)
    with open(filename, newline='', encoding='utf-8') as csvfile:
        books = csv.reader(csvfile, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        next(csvfile)
        for book in books:
            # Seems to be some ampersands are encoded as HTML entities in data,
            # replace with ampersand char
            book_title = book[1].replace('&amp;', '&')
            # Detect the language of the title and only use english ones
            book_title_lang = detect_language(book_title)
            if book_title_lang == 'english':
                # Get details of the book from Wikipedia
                details = get_book_infoblock_plot(
                        extract_title_parts(book_title))
                if 'wiki_id' in details.keys():
                    # Perform a NLTK analysis of contents to locate any
                    # locations
                    extract_named_entities(details['content'])

                    # Add to index
                    writer.add_document(details)

        writer.commit()

    pprint(list(nr_idx.searcher().documents()))


if __name__ == '__main__':

    default_index = os.getcwd() + "/index/nomadreader.idx"

    parser = arg.ArgumentParser(
        description="""Process a CSV file of ISBN, book title, author, pub year
        and index it with  """)
    parser.add_argument('-f', '--file', dest='filename', required=True)
    parser.add_argument('-i', '--index', dest='indexname',
                        default=default_index, required=False)
    args = parser.parse_args()

    main(args.filename, args.indexname)

    # reddit = praw.Reddit('nomadreader')
    #
    # subreddit = reddit.subreddit('Book_Recommendations')
    # for recommends in subreddit.hot():
    #     if recommends.title.lower().startswith('[recommend me]'):
    #         for recommend in recommends.comments:
    #             print(recommends.title)
    #             print(recommend.body)
    #             print("\n")
