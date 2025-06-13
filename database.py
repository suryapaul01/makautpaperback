from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

# Association table for many-to-many relationship between users and purchased papers
purchased_papers_association = Table(
    'purchased_papers',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('paper_id', Integer, ForeignKey('question_papers.id'))
)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    stars = Column(Integer, default=0)

    purchased_papers = relationship("QuestionPaper", secondary=purchased_papers_association, back_populates="purchasers")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, stars={self.stars})>"

class QuestionPaper(Base):
    __tablename__ = 'question_papers'
    id = Column(Integer, primary_key=True)
    department = Column(String, nullable=False)
    semester = Column(String, nullable=False)
    year = Column(String, nullable=False)
    paper_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    price = Column(Integer, default=10) # Default price is 10 stars

    purchasers = relationship("User", secondary=purchased_papers_association, back_populates="purchased_papers")

    def __repr__(self):
        return f"<QuestionPaper(department={self.department}, semester={self.semester}, year={self.year}, paper_name={self.paper_name})>"


# Database setup
DATABASE_URL = "sqlite:///./bot.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 