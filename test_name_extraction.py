import pytest

import reddomendation as rd


# Test to ensure an author name is correctly parsed
@pytest.mark.parametrize(
    'author_name,expected', [
        ('William Gibson', {
            'first': 'William',
            'middle': '',
            'last': 'Gibson'
        }),
        ('Bret Easton Ellis', {
            'first': 'Bret',
            'middle': 'Easton',
            'last': 'Ellis'
        }),
        ('George A. Beavers', {
            'first': 'George',
            'middle': 'A.',
            'last': 'Beavers'
        }),
        ('A. Writer', {
            'first': 'A.',
            'middle': '',
            'last': 'Writer'
        }),
        ('A. A. Milne', {
            'first': 'A.',
            'middle': 'A.',
            'last': 'Milne'
        }),
        ('J.R.R. Tolkien', {
            'first': 'J.',
            'middle': 'R. R.',
            'last': 'Tolkien'
        })
    ])
def test_name_extraction(author_name, expected):
    result = rd.extract_name_parts(author_name)
    assert expected == result


# Test to ensure a author name dict is correctly translated to string
@pytest.mark.parametrize(
    'author_dict,expected', [
        ({
            'first': 'William',
            'middle': '',
            'last': 'Gibson'
        }, 'William_Gibson'),
        ({
            'first': 'William',
            'last': 'Gibson'
        }, 'William_Gibson'),
        ({
            'first': 'Bret',
            'middle': 'Easton',
            'last': 'Ellis'
        }, 'Bret_Easton_Ellis'),
        ({
            'first': 'George',
            'middle': 'A.',
            'last': 'Beavers'
        }, 'George_A._Beavers'),
        ({
            'first': 'A.',
            'middle': '',
            'last': 'Writer'
        }, 'A._Writer'),
        ({
            'first': 'A.',
            'middle': 'A.',
            'last': 'Milne'
        }, 'A._A._Milne'),
        ({
            'first': 'J.',
            'middle': 'R. R.',
            'last': 'Tolkien'
        }, 'J._R._R._Tolkien'),
        ({
            'first': 'Jean',
            'middle': 'le Rond',
            'last': "D'Alembert"
        }, 'Jean_le_Rond_d%27Alembert')
    ])
def test_author_wiki_slug_generation(author_dict, expected):
    result = rd.create_wiki_name_slug(author_dict)
    assert expected == result


# Test to ensure a book title is correctly parsed
@pytest.mark.parametrize(
    'book_title,expected', [
        ('The Castle', {
            'title': 'The Castle',
            'subtitle': ''
        }),
        ('Something Comes (Ballentine Book)', {
            'title': 'Something Comes',
            'subtitle': ''
        }),
        ('Flood: Mississippi 1927', {
            'title': 'Flood',
            'subtitle': 'Mississippi 1927'
        })
    ])
def test_title_extraction(book_title, expected):
    result = rd.extract_title_parts(book_title)
    assert expected == result


# Test to ensure a book title name dict is correctly translated to string
@pytest.mark.parametrize(
    'book_dict,expected', [
        ({
            'title': 'The Castle',
            'subtitle': ''
        }, 'The_Castle'),
        ({
            'title': 'Something Comes',
            'subtitle': ''
        }, 'Something_Comes', ),
        ({
            'title': 'Flood',
            'subtitle': 'Mississippi 1927'
        }, 'Flood%3A_Mississippi_1927')
    ])
def test_title_wiki_slug_generation(book_dict, expected):
    result = rd.create_wiki_title_slug(book_dict)
    assert expected == result
