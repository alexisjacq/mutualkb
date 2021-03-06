import logging
logger = logging.getLogger('mylog')
DEBUG_LEVEL=logging.DEBUG

import sqlite3

KBNAME = 'kb.db'
TABLENAME = 'nodes'
TABLE = ''' CREATE TABLE IF NOT EXISTS %s
            ("subject" TEXT NOT NULL ,
            "predicate" TEXT NOT NULL ,
            "object" TEXT NOT NULL ,
            "model" TEXT NOT NULL ,
            "trust" FLOAT DEFAULT 0.5 NOT NULL,
            "active" INT DEFAULT 0 NOT NULL,
            "matter" FLOAT DEFAULT 0.5 NOT NULL,
            "infered" BOOLEAN DEFAULT 1 NOT NULL,
            "modified" BOOLEAN DEFAULT 1 NOT NULL,
            "id" TEXT PRIMARY KEY NOT NULL UNIQUE)'''

#DEFAULT_MODEL = 'K_myself'


class KB:

    def __init__(self):
        self.conn = sqlite3.connect(KBNAME)
        self.create()
        self.clear()
        logger.info('new knowledge base created')

    def create(self):
        with self.conn:
            self.conn.execute(TABLE % TABLENAME)

    def clear(self):
        with self.conn:
            self.conn.execute('''DELETE FROM %s''' % TABLENAME)

    def save(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def wait_turn(self):
        while True:
            try:
                self.conn.execute('''SELECT * FROM %s''' % TABLENAME)
                break
            except sqlite3.OperationalError:
                pass



    # ADD methods
    #-------------------------

    def add(self, stmts, model, trust=None):
        ''' stmts = statements = list of triplet 'subject, predicate, object'. ex: [[ s1, p1, o1], [s2, p2, o2], ...]
        this methode adds nodes to the table with statments attached to the selected model and increases trusts
        it returns a list of value that measur the importance of the added nodes to capt attention'''

        if trust or trust==0:
            llh = trust
        else:
            llh = 0.5

        self.wait_turn()

        new_stmts = []
        for s,p,o in stmts:
            if o=='?':
                stmts_to_add = {(s, p, row[0]) for row in self.conn.execute(
                            '''SELECT object FROM %s WHERE
                            model="%s" AND subject="%s" AND predicate="%s" ''' % (TABLENAME, model,s,p))}
                if stmts_to_add:
                    for stmt in stmts_to_add:
                        new_stmts.append(stmt)
                else:
                    new_stmts.append([s,p,'??'])
            else:
                new_stmts.append([s,p,o])

        stmts = new_stmts


        ids = [("%s%s%s%s"%(s,p,o, model),) for s,p,o in stmts]
        node_ids = [("%s%s%s%s"%(s,p,o, model)) for s,p,o in stmts]


        for node_id in ids:
            cursor=self.conn.cursor()
            try:
                cursor.execute('''SELECT trust FROM %s WHERE (id = ?)''' % TABLENAME, node_id)
                hold_llh = cursor.fetchone()[0]
            except TypeError:
                hold_llh = 0
            matter = abs(llh-hold_llh)
            self.conn.executemany('''UPDATE %s SET matter='%f' WHERE id=?''' % (TABLENAME, matter), ids)

        nodes = [[ s, p, o, model, 0, "%s%s%s%s"%(s,p,o, model) ] for s,p,o in stmts]
        self.conn.executemany('''INSERT OR IGNORE INTO %s
                       (subject, predicate, object, model, infered, id )
                       VALUES (?, ?, ?, ?, ?, ?)''' % TABLENAME, nodes)

        self.conn.executemany('''UPDATE %s SET modified = 1
                            WHERE id=?''' % TABLENAME, ids)

        if trust or trust==0:

            llh = trust
            for node in node_ids:
                cur = self.conn.execute('''SELECT trust FROM %s WHERE id=?'''% TABLENAME, [node])
                lh = cur.fetchone()[0]
                trust = llh
                if(lh-llh)*(lh-llh) == 1:
                    # choose the new one
                    pass
                else:
                    trust = lh*llh/( lh*llh + (1-lh)*(1-llh) )

                self.conn.execute(''' UPDATE %s SET trust=%f 
                                    WHERE id=?''' % (TABLENAME, trust), [node])
        self.save()


    def sub(self, stmts, model, untrust=None):
        ''' the unlikeliihood is the trust for the statement to be false, for ex, the trust of a contrary statement '''
        '''stmts = this methode decreases trusts of nodes with statments attached to the selected model '''

        self.wait_turn

        ids = [("%s%s%s%s"%(s,p,o, model),) for s,p,o in stmts]

        if untrust:
            self.conn.executemany('''UPDATE %s SET trust=((SELECT trust)*(1-%f)
                          /((SELECT trust)*(1-%f) + (1-(SELECT trust))*(%f))) 
                          WHERE id=?''' % (TABLENAME, untrust, untrust, untrust) , ids)
        self.save()


    # THOUGHT methods
    #----------------------------


    def get_attractive_nodes(self,threshold):
        nodes = {(row[0], row[1]) for row in self.conn.execute('''SELECT id, matter FROM %s WHERE matter>%f''' %(TABLENAME, threshold))}
        return nodes

    def get_actives_nodes(self):
        nodes = {(row[0], row[1]) for row in self.conn.execute('''SELECT id, active FROM %s WHERE active>0''' %(TABLENAME))}
        return nodes

    def get_thought(self):
        inThought = {(row[0], row[1], row[2], row[3], row[4], row[5]) for row in self.conn.execute(
                    '''SELECT subject, predicate, object, trust, model, active FROM %s WHERE active>0''' %(TABLENAME))}
        return inThought

    def fire(self, node_id, fire_time):
        ''' actives the selected nodes'''
        self.wait_turn()
        self.conn.execute('''UPDATE %s SET active = %i WHERE id=?''' % (TABLENAME, fire_time), (node_id,))
        self.conn.commit()
        #time.sleep(1/THOUGHT_RATE)

    def clock(self):
        ''' update the time each node keeps firing '''
        self.wait_turn()
        self.conn.execute('''UPDATE %s SET active = (SELECT active)-1 WHERE active>0''' % TABLENAME)
        self.conn.commit()

    def douse(self):
        ''' disactives the time-out nodes '''
        self.wait_turn()
        self.conn.execute('''UPDATE %s SET matter=0 WHERE active>0.1 ''' % TABLENAME)
        self.conn.commit()

    def kill(self, node_id):
        ''' removes the selected nodes '''
        self.wait_turn()
        self.conn.execute('''DELETE FROM %s WHERE id=?''' % TABLENAME, (node_id,))
        self.conn.commit()

        # TEST methods
    #---------------------------------

    def isUmpty(self):
        try:
            test = self.conn.execute('''SELECT * FROM %s''' % TABLENAME )
        except sqlite3.OperationalError:
            test = {}
        if test:
            return False
        else:
            return True

    def get_trust(self, node_id):
        try:
            trust = self.conn.execute('''SELECT trust FROM %s WHERE id="%s" '''%(TABLENAME, node_id))
            return trust.fetchone()[0]
        except sqlite3.OperationalError:
            return None


    def contains(self, stmts, model):

        node_ids = [("%s%s%s%s"%(s,p,o, model)) for s,p,o in stmts]

        test = True
        for node_id in node_ids:
            node = self.conn.execute('''SELECT * FROM %s WHERE id="%s" '''%(TABLENAME, node_id))
            if not node.fetchone()==None:
                pass
            else:
                test = False
                break

        return test





