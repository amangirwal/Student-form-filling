from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database setup
DATABASE_URL = "sqlite:///students.db"  # You can use PostgreSQL or MySQL as well

engine = create_engine(DATABASE_URL)
Base = declarative_base()

# Student model
class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    student_id = Column(String, nullable=False)
    certificate_url = Column(String, nullable=True)
    certificate_file_name = Column(String, nullable=True)

# Create table
Base.metadata.create_all(engine)

# Database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
