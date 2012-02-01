import MySQLdb
import MySQLdb.cursors
import os.path
import sys
from datetime import datetime

class db_conn:

        def __init__(self):
                assert MySQLdb.paramstyle == 'format'

        def connect(self):
                self.db = MySQLdb.connect(host='localhost',user='root', db='powerlogs')
                self.c = self.db.cursor()

        def insert_row(self,table,fields,values):
                cmd = 'INSERT INTO %s ' % table
                field_fmt = '('
                for each in fields:
                        field_fmt += '%s,' % each
                field_fmt = field_fmt[:-1] + ') '
                value_fmt = 'VALUES ('
                for each in values:
                        if isinstance(each,int):
                                value_fmt += '%d,' % each
                        elif isinstance(each,long):
                                value_fmt += '%d,' % each
                        elif isinstance(each,str):
                                value_fmt += "'%s'," % each
                        elif isinstance(each,float):
                                value_fmt += '%f,' % each
                        elif isinstance(each,datetime):
                                value_fmt += "'%s'," % str(each)[:-6]
                        else:
                                print "unknown type %s of %s" % (type(each),repr(each))

                value_fmt = value_fmt[:-1] + ')'
                cmd += field_fmt + value_fmt + ';'
                self.c.execute(cmd)

        def do_query(self,sql):
                self.c.execute(sql)

        def get_row(self):
                return self.c.fetchone()
