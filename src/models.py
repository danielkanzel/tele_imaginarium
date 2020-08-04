import sqlalchemy

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    users = db.Column(db.String(10240), unique=True, nullable=False)
    turns = db.Column(db.String(10240), unique=True, nullable=False)

    def __repr__(self):
        return '<Game %r>' % self.id