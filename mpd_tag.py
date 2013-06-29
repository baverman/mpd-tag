import sys
import os.path
import argparse
import sqlite3
import ast
import locale
import codecs

TERM_ENCODING = locale.getdefaultlocale()[1]

VERSION = '0.4dev'

def execute_sql(conn, sql, params):
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
    except sqlite3.OperationalError, e:
        if ': tags' in e.message:
            conn.execute('CREATE TABLE tags (path text, tag text,'
                'value INTEGER, UNIQUE(path, tag) ON CONFLICT REPLACE)')
            cur.execute(sql, params)
            conn.commit()
        else:
            raise

    return cur

def add_tags(conn, path, *tags, **valued_tags):
    sql = 'INSERT INTO tags (path, tag, value) VALUES (?, ?, ?)'
    for tag in tags:
        execute_sql(conn, sql, (path, tag, None))

    for tag, value in valued_tags.items():
        execute_sql(conn, sql, (path, tag, value))

def remove_tags(conn, path, *tags):
    if not tags:
        execute_sql(conn, 'DELETE FROM tags WHERE path=?', [path])
    else:
        execute_sql(conn,
            'DELETE FROM tags WHERE path=? and tag IN (%s)' % ','.join('?'*len(tags)), (path,) + tags)

def set_tags(conn, path, *tags, **valued_tags):
    remove_tags(conn, path)
    add_tags(conn, path, *tags, **valued_tags)

def get_tags(conn, path):
    result = execute_sql(conn, 'SELECT * FROM tags WHERE path=?', [path])
    return dict((r[1], r[2]) for r in result)


class ExprGenerator(ast.NodeVisitor):
    def __init__(self):
        self.expr = ''
        self.params = []

    def visit_Name(self, node):
        tag_name = node.id
        if tag_name == 'anytag':
            self.expr += 'EXISTS (select tag from tags where path = _p)'
        else:
            self.expr += 'EXISTS (select tag from tags where path = _p and tag = ?)'
            self.params.append(tag_name)

    def visit_BoolOp(self, node):
        op_name = {ast.And:' and ', ast.Or:' or '}[node.op.__class__]

        self.expr += '('
        self.visit(node.values[0])
        self.expr += ')'
        for v in node.values[1:]:
            self.expr += op_name
            self.expr += '('
            self.visit(v)
            self.expr += ')'

    def visit_UnaryOp(self, node):
        op_name = {ast.Not:'not '}[node.op.__class__]
        self.expr += op_name
        self.expr += '('
        self.visit(node.operand)
        self.expr += ')'

    def visit_Compare(self, node):
        op_names = {
            ast.Gt:  '>',
            ast.GtE: '>=',
            ast.Lt:  '<',
            ast.LtE: '<=',
            ast.Eq:  '=',
        }

        left = node.left
        self.expr += 'EXISTS (select tag from tags where path = _p'
        tag_added = [False]

        def add_tag(r):
            if not tag_added[0]:
                self.expr += ' and tag = ?'
                self.params.append(r.id)
                tag_added[0] = True

        for op, right in zip(node.ops, node.comparators):
            op_name = op_names[op.__class__]
            if left.__class__ is ast.Num:
                assert right.__class__ is ast.Name, 'Right side of compare must be a name'
                add_tag(right)
                self.expr += ' and ? %s value' % op_name
                self.params.append(left.n)

            elif left.__class__ is ast.Name:
                assert right.__class__ is ast.Num, 'Right side of compare must be a number'
                add_tag(left)
                self.expr += ' and value %s ?' % op_name
                self.params.append(right.n)
            else:
                assert False, 'Invalid compare'

            left = right

        self.expr += ')'


def generate_sql_expr(query):
    node = ast.parse(query)
    g = ExprGenerator()
    g.generic_visit(node)
    return g.expr, g.params

def find(conn, query, root=None):
    expr, params = generate_sql_expr(query)
    result = execute_sql(conn, 'SELECT DISTINCT path as _p FROM tags WHERE ' + expr, params)
    return [r[0] for r in result]


###########################################
# CLI interface

def get_mpd_client(client=[]):
    if not client:
        import mpd
        addr = os.environ.get('MPD_HOST', 'localhost:6600')
        host, _, port = addr.partition(':')
        c = mpd.MPDClient()
        c.connect(host, port)
        client.append(c)

    return client[0]

def get_sources(args):
    if args.file:
        return [args.file.decode(TERM_ENCODING)]
    elif args.filelist:
        if args.filelist == '-':
            f = sys.stdin
        else:
            f = open(args.filelist)

        return (l.rstrip('\r\n') for l in f)
    elif args.playlist:
        return (r['file'].decode('utf-8') for r in get_mpd_client().playlistinfo())
    else:
        if args.filter:
            return []
        else:
            return [get_mpd_client().currentsong()['file'].decode('utf-8')]

def process_playlist_actions(sources, args):
    if args.use_as_playlist:
        c = get_mpd_client()
        c.command_list_ok_begin()

        if not args.add_to_playlist:
            c.clear()

        for r in sources:
            c.add(r.encode('utf-8'))

        c.command_list_end()

def filter_sources(sources, args, conn):
    if args.filter:
        if sources:
            matched = set(find(conn(), args.filter))

            if args.remove:
                result = (r for r in sources if r not in matched)
            else:
                result = (r for r in sources if r in matched)
        else:
            result = find(conn(), args.filter)

        return result
    else:
        return sources

def show_all_tags(conn):
    conn = conn()
    for r in execute_sql(conn, 'SELECT DISTINCT tag FROM tags', []):
        print r[0]

def show_with_tags(sources, conn):
    conn = conn()
    for r in sources:
        tags = get_tags(conn, r)
        tags_str = ' '.join(k if v is None else ('%s=%s' % (k,v)) for k, v in tags.items())
        print u'{}\t{}'.format(tags_str, r)

def show_without_tags(sources):
    for r in sources:
        print r

def parse_tags_with_values(args):
    tags, valued_tags = [], {}
    for r in args:
        if '=' in r:
            tag, _, value = r.partition('=')
            valued_tags[tag] = value
        else:
            tags.append(r)

    return tags, valued_tags

def process_tag_actions(sources, args, conn):
    conn = conn()
    if args.clear:
        for r in sources:
            remove_tags(conn, r)

    if args.delete:
        for r in sources:
            remove_tags(conn, r, *args.delete)

    if args.set:
        tags, vtags = parse_tags_with_values(args.set)
        for r in sources:
            set_tags(conn, r, *tags, **vtags)

    if args.add:
        tags, vtags = parse_tags_with_values(args.add)
        for r in sources:
            add_tags(conn, r, *tags, **vtags)

def run():
    parser = argparse.ArgumentParser()

    parser.add_argument('--db', dest='db',
        help="Specify alternative tag db location")

    source = parser.add_mutually_exclusive_group()
    source.add_argument('-i', dest='file')
    source.add_argument('-l', dest='filelist', nargs='?', const='-')
    source.add_argument('-p', dest='playlist', action='store_true')

    parser.add_argument('-f', dest='filter')
    parser.add_argument('-r', dest='remove', action='store_true')
    
    parser.add_argument('-S', dest='set', nargs='+')
    parser.add_argument('-A', dest='add', nargs='+')
    parser.add_argument('-D', dest='delete', nargs='+')
    parser.add_argument('-C', dest='clear', action='store_true')

    parser.add_argument('-T', dest='alltags', action='store_true')
    
    parser.add_argument('-P', dest='use_as_playlist', action='store_true')

    parser.add_argument('-n', dest='only_filenames', action='store_true')
    parser.add_argument('-a', dest='add_to_playlist', action='store_true')

    parser.add_argument('--version', action='version', version=VERSION)

    parser.set_defaults(db=os.path.join(os.getenv('XDG_DATA_HOME',
        os.path.expanduser('~/.local/share')), 'mpd_tag', 'tags.sqlite'))

    args = parser.parse_args()

    dirname = os.path.dirname(args.db)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    def conn(cn=[]):
        if not cn:
            cn.append(sqlite3.connect(args.db))

        return cn[0]

    sys.stdout = codecs.getwriter(TERM_ENCODING)(sys.stdout)
    sys.stdin = codecs.getreader(TERM_ENCODING)(sys.stdin)

    if args.alltags:
        show_all_tags(conn)
    else:
        sources = get_sources(args)
        sources = filter_sources(sources, args, conn)

        process_tag_actions(sources, args, conn)
        process_playlist_actions(sources, args)

        if args.only_filenames:
            show_without_tags(sources)
        else:
            show_with_tags(sources, conn)
