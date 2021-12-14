import pytest

import reddomendation as rd
import pywikibot as wiki
from pywikibot import pagegenerators as pg

from pprint import pprint


@pytest.mark.skip
def test_wiki_list_books():
    site = wiki.Site()
    name = "{}:{}".format(site.namespace(10), "Infobox book")
    tmpl_page = wiki.Page(site, name)
    ref_gen = pg.ReferringPageGenerator(tmpl_page, onlyTemplateInclusion=True)
    filter_gen = pg.NamespaceFilterPageGenerator(ref_gen, namespaces=[0])
    generator = site.preloadpages(filter_gen, pageprops=True)

    for page in generator:
        item = wiki.ItemPage.fromPage(page)
        pprint(page.title())
        item_details = item.get()
        for claim_key, claim_val in item_details['claims'].items():
            for claim in claim_val:
                clm_trgt = claim.getTarget()
                pprint(clm_trgt)
                pprint(type(clm_trgt))
                # pprint(dir(clm_trgt))
                break
        break

    assert True


def test_wiki_cat_books():
    site = wiki.Site()
    cat = wiki.Category(site, 'Category:Novels')
    # gen = pg.CategorizedPageGenerator(cat)
    for page in cat.articles(recurse=2):
        # Do something with the page object, for example:
        for template in page.templates():
            print(page.title())
            pprint('##################################')
        # print(type(item), item.title())

    assert True

#
# # Test to ensure an author name is correctly parsed
# @pytest.mark.parametrize(
#     'author_name,expected', [
#         ('William Gibson', {
#             'first': 'William',
#             'middle': '',
#             'last': 'Gibson'
#         }),
#         ('Bret Easton Ellis', {
#             'first': 'Bret',
#             'middle': 'Easton',
#             'last': 'Ellis'
#         }),
#         ('George A. Beavers', {
#             'first': 'George',
#             'middle': 'A.',
#             'last': 'Beavers'
#         }),
#         ('A. Writer', {
#             'first': 'A.',
#             'middle': '',
#             'last': 'Writer'
#         }),
#         ('A. A. Milne', {
#             'first': 'A.',
#             'middle': 'A.',
#             'last': 'Milne'
#         }),
#         ('J.R.R. Tolkien', {
#             'first': 'J.',
#             'middle': 'R. R.',
#             'last': 'Tolkien'
#         })
#     ])
# def test_wiki_parsing_nonexisting(author_name, expected):
#     result = rd.extract_name_parts(author_name)
#     assert expected == result
