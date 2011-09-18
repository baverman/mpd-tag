import sqlite3

from mpd_tag import add_tags, execute_sql, set_tags, get_tags, find, remove_tags

def pytest_funcarg__conn(request):
    return sqlite3.connect(':memory:')

def test_execute_sql_must_create_tags_table_on_demand(conn):
    execute_sql(conn, 'insert into tags values (?, ?, ?)', ['song', 'tag', 10])
    result = execute_sql(conn, 'select * from tags', []).fetchall()

    assert result == [('song', 'tag', 10)]

def test_one_must_be_able_to_set_and_get_tags_for_path(conn):
    set_tags(conn, 'song1', 'rus', rating=10, mood=5)
    set_tags(conn, 'song2', vol=2, rocking=3)

    result = get_tags(conn, 'song1')
    assert result == {'rus':None, 'rating':10, 'mood':5}

    result = get_tags(conn, 'song2')
    assert result == {'vol':2, 'rocking':3}

def test_one_must_be_able_to_update_tags(conn):
    set_tags(conn, 'song', vol=2, rocking=3)
    add_tags(conn, 'song', vol=4, rating=5)

    result = get_tags(conn, 'song')
    assert result == {'vol':4, 'rating':5, 'rocking':3}

def test_one_must_be_able_to_remove_specific_tags(conn):
    set_tags(conn, 'song', vol=2, rocking=3)
    remove_tags(conn, 'song', 'vol')

    result = get_tags(conn, 'song')
    assert result == {'rocking':3}

def test_seg_one_name(conn):
    set_tags(conn, 'song1', 'rating')
    set_tags(conn, 'song2', rating=10)
    set_tags(conn, 'song3', rate=1)

    result = find(conn, 'rating')
    assert result == ['song1', 'song2']

def test_seg_multy_name(conn):
    set_tags(conn, 'song1', 'rating', 'mood')
    set_tags(conn, 'song2', 'rating')
    set_tags(conn, 'song3', 'mood')

    result = find(conn, 'rating and mood')
    assert result == ['song1']

    result = find(conn, 'rating or mood')
    assert result == ['song1', 'song2', 'song3']

def test_seg_not_name(conn):
    set_tags(conn, 'song1', 'rating', 'mood')
    set_tags(conn, 'song2', 'rating')
    set_tags(conn, 'song3', 'mood')

    result = find(conn, 'not rating and mood')
    assert result == ['song3']

def test_seg_compare(conn):
    set_tags(conn, 'song1', rating=3)
    set_tags(conn, 'song2', rating=5)
    set_tags(conn, 'song3', rating=10)
    set_tags(conn, 'song4', rate=9)

    result = find(conn, 'rating > 5')
    assert result == ['song3']

    result = find(conn, 'rating >= 5')
    assert result == ['song2', 'song3']

    result = find(conn, 'rating < 5')
    assert result == ['song1']

    result = find(conn, 'rating <= 5')
    assert result == ['song1', 'song2']

    result = find(conn, 'rating == 5')
    assert result == ['song2']

    result = find(conn, '3 < rating < 10')
    assert result == ['song2']

def test_seg_complex(conn):
    set_tags(conn, 'song1', 'mood', rating=5)
    set_tags(conn, 'song2', 'mood', rating=10)
    set_tags(conn, 'song3', rating=10)

    result = find(conn, 'rating > 5 and mood')
    assert result == ['song2']

def test_seg_anytag(conn):
    set_tags(conn, 'song1', 'mood', rating=5)
    set_tags(conn, 'song2', 'mood', rating=10)
    set_tags(conn, 'song3', rating=10)

    result = find(conn, 'anytag')
    assert result == ['song1', 'song2', 'song3']
