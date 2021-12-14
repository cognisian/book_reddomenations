import pytest

import os

import Book as bk
import json


str_repr_fixture = ("{'isbn': '00', 'asin': '', 'title': 'Test', 'rank': 0, "
                    "'authors': None, 'city': '', 'country': '', "
                    "'latitude': 0.0, 'longitude': 0.0, 'periods': [], "
                    "'genres': [], 'image': '', 'ratings': {}, "
                    "'readability': 0, 'story_arc': (), "
                    "'where_to_read': '', 'word_cloud': '', 'summary': ''}"
                    )
csv_dict_fixture = {'isbn': '00', 'asin': '', 'title': 'Test', 'rank': 0,
                    'authors': None, 'city': '', 'country': '',
                    'latitude': 0.0, 'longitude': 0.0, 'periods': None,
                    'genres': None, 'image': '', 'ratings': None,
                    'readability': 0, 'story_arc': None,
                    'where_to_read': '', 'word_cloud': '', 'summary': ''}


@pytest.fixture()
def book():
    return bk.Book(isbn='00', title='Test')


@pytest.fixture()
def real_book():
    return bk.Book(isbn='0006485324', title='Headhunter',
                   authors="Timothy Findley")


def test_to_dict(book):

    rep = book.to_dict()

    assert rep == csv_dict_fixture


def test_book_setters(book):
    """ Test to ensure that attributes which accept comma separated values is
    translated into a list
    """

    authors_fixture = "Some One, Someone Else"
    author_result = ["Some One", "Someone Else"]

    periods_fixture = "Historical, 1920s"
    periods_result = ["Historical", "1920s"]

    genres_fixture = "SciFi, Horror"
    genres_result = ["SciFi", "Horror"]

    city_fixture = "Toronto"
    city_country_fixture = "Toronto, Canada"
    city_result = "Toronto"
    country_result = "Canada"

    # Test that constructor creates empty lists
    assert book.authors is None
    assert book.periods is None
    assert book.genres is None
    assert book.city == ''
    assert book.country == ''

    # Test that setters from strings create lists
    book.authors = authors_fixture
    assert book.authors == author_result

    book.periods = periods_fixture
    assert book.periods == periods_result

    book.genres = genres_fixture
    assert book.genres == genres_result

    book.city = city_fixture
    assert book.city == city_result
    assert book.country == ''

    book.city = book.split_city_country(city_country_fixture)[0]
    book.country = book.split_city_country(city_country_fixture)[1]
    assert book.city == city_result
    assert book.country == country_result


def test_json_encoded_decoded(book):

    filename = os.path.join(os.getcwd(), 'test.json')
    with open(filename, 'w') as db_file:
        data = json.dumps(list(map(lambda book: book.to_dict(),
                                   [book])),
                          indent=2)
        db_file.write(data)

    with open(filename, 'r') as db_file:
        data = db_file.read()
        loaded_book = bk.Book(**(json.loads(data)[0]))

        assert book.isbn == loaded_book.isbn
        assert book.title == loaded_book.title


def test_amazon_reviews(real_book):

    real_book.get_details_amazon_review()

    test_review = {
        'rating': 5.0,
        'num_ratings': 9
    }
    assert real_book.ratings == test_review


@pytest.mark.parametrize(
    'isbn, expected', [
        ('0006485324', {
            'asin': '0006485324',
            'image':
            'https://images-na.ssl-images-amazon.com/images/I/51YiHyV3JjL.jpg',
            'readability': 132000
        })
    ])
def test_retrieve_amazon_details_no_summary(isbn, expected):

    test = 'Test Summary'
    book = bk.Book(isbn, summary=test)

    book.get_details_amazon()

    assert book.asin == expected['asin']
    assert book.image == expected['image']
    assert book.readability == expected['readability']
    assert book.summary == test


@pytest.mark.parametrize(
    'isbn, expected', [
        ('0006485324', {
            'asin': '0006485324',
            'image':
            'https://images-na.ssl-images-amazon.com/images/I/51YiHyV3JjL.jpg',
            'readability': 132000
        })
    ])
def test_retrieve_amazon_details_with_summary(isbn, expected):

    book = bk.Book(isbn)

    book.get_details_amazon()

    assert book.asin == expected['asin']
    assert book.image == expected['image']
    assert book.readability == expected['readability']
    assert book.summary != ''


@pytest.mark.parametrize(
    'isbn, city, expected', [
        ('0006485324', 'Toronto', {
            'country': 'Canada',
            'latitude': 43.653963,
            'longitude': -79.387207
        })
    ])
def test_retrieve_geoloc_details(isbn, city, expected):

    book = bk.Book(isbn, city=city)

    book.get_details_geolocation()

    assert book.city == city
    assert book.country == expected['country']
    assert book.latitude == expected['latitude']
    assert book.longitude == expected['longitude']


@pytest.mark.parametrize(
    'isbn, city, expected', [
        ('000721829X', 'London', {
            'country': 'England',
            'latitude': 51.50853,
            'longitude': -0.12574
        })
    ])
def test_retrieve_cached_geoloc_details(isbn, city, expected):

    book = bk.Book(isbn, city=city)

    book.get_details_geolocation()

    assert book.city == city
    assert book.country == expected['country']
    assert book.latitude == expected['latitude']
    assert book.longitude == expected['longitude']
