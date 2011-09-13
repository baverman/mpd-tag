import sqlite3
import ast

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

def remove_tags(conn, path):
    execute_sql(conn, 'DELETE FROM tags WHERE path=?', [path])

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
        self.expr += 'EXISTS (select tag from tags where path = _p and tag = ?)'
        self.params.append(node.id)

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

def run():
    pass