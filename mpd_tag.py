import sys
import os.path
import optparse
import sqlite3
import ast
import locale
import codecs

TERM_ENCODING = locale.getdefaultlocale()[1]

VERSION = '0.3'

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
        c = mpd.MPDClient()
        c.connect('/var/run/mpd/socket', None)
        client.append(c)

    return client[0]

def get_input(input_source):
    if input_source == 'current or stdin':
        input_source = 'current' if sys.stdin.isatty() else '-'

    if input_source == '-':
        return (l.rstrip('\r\n') for l in sys.stdin)
    elif input_source == 'current':
        return [get_mpd_client().currentsong()['file'].decode('utf-8')]
    elif input_source == 'playlist':
        return (r['file'].decode('utf-8') for r in get_mpd_client().playlistinfo())
    else:
        return [input_source.decode(TERM_ENCODING)]

input_help = '''Input can be one of:

  current  - current playlist song
  playlist - songs from playlist
  dash(-)  - songs from stdin (for example mpc playlist -f %%file%% | %prog add -i - rating=10)

or simply path/to/song.'''

def add_input_option(parser, default):
    parser.add_option('-i', '', dest='input',
    help='Songs source. Default is %default.',
    default=default)

def do_set(args, conn):
    p = optparse.OptionParser(usage='%prog set [-i input] tag1 tag2=value ...\n\n' + input_help)
    add_input_option(p, 'current or stdin')
    option, args = p.parse_args(args)

    tags, valued_tags = [], {}
    for r in args:
        if '=' in r:
            tag, _, value = r.partition('=')
            valued_tags[tag] = value
        else:
            tags.append(r)

    conn = conn()
    for r in get_input(option.input):
        set_tags(conn, r, *tags, **valued_tags)
        print r

def do_add(args, conn):
    p = optparse.OptionParser(usage='%prog add [-i input] tag1 tag2=value ...\n\n' + input_help)
    add_input_option(p, 'current or stdin')
    option, args = p.parse_args(args)

    tags, valued_tags = [], {}
    for r in args:
        if '=' in r:
            tag, _, value = r.partition('=')
            valued_tags[tag] = value
        else:
            tags.append(r)

    conn = conn()
    for r in get_input(option.input):
        add_tags(conn, r, *tags, **valued_tags)
        print r

def do_find(args, conn):
    for r in find(conn(), args[0]):
        print r

def do_show(args, conn):
    p = optparse.OptionParser(usage='%prog show [-i input] [alltags]\n\n' + input_help)
    add_input_option(p, 'current or stdin')
    option, args = p.parse_args(args)

    conn = conn()
    if args and args[0] == 'alltags':
        for r in execute_sql(conn, 'SELECT DISTINCT tag FROM tags', []):
            print r[0]
    else:
        for r in get_input(option.input):
            tags = get_tags(conn, r)
            print r
            print ', '.join(k if v is None else ('%s=%s' % (k,v)) for k, v in tags.items())
            print

def do_del(args, conn):
    p = optparse.OptionParser(usage='%prog del [-i input] tag1 tag2...\n\n' + input_help)
    add_input_option(p, 'current or stdin')
    option, args = p.parse_args(args)

    conn = conn()
    for r in get_input(option.input):
        remove_tags(conn, r, *args)
        print r


def run():
    usage = '''%prog [mtag options] CMD [command options]

Where CMD is one of:

  add  - append or change tags
  set  - create or replace tags
  find - search songs by createria
  show - display various info
  del  - remove tags'''

    p = optparse.OptionParser(usage=usage, version='%prog ' + VERSION)
    p.add_option('-d', '--db', dest='db',
        help="Specify alternative tag db location. Default is %default")
    p.disable_interspersed_args()
    p.set_defaults(db=os.path.join(os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share')),
        'mpd_tag', 'tags.sqlite'))

    option, args = p.parse_args()

    dirname = os.path.dirname(option.db)
    if not os.path.exists(dirname):
        os.makedirs(dirname, 0755)

    def conn(cn=[]):
        if not cn:
            cn.append(sqlite3.connect(option.db))

        return cn[0]

    if not args:
        p.error('You should specify command')

    cmd_name = args[0]
    handler = globals().get('do_' + cmd_name, None)

    if not handler:
        p.error('Unknown command: %s' % cmd_name)

    sys.stdout = codecs.getwriter(TERM_ENCODING)(sys.stdout)
    sys.stdin = codecs.getreader(TERM_ENCODING)(sys.stdin)

    handler(args[1:], conn)
