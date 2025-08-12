import os

from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine
from dotenv import load_dotenv

def get_db_connection():
    load_dotenv()

    connector = Connector()

    def get_connection():
        return connector.connect(
            os.getenv("GCP_CLOUD_SQL_CONNECTION_NAME"),
            "pymysql",
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"), 
            db=os.getenv("MYSQL_DB_NAME"),
        )

    return create_engine("mysql+pymysql://", creator=get_connection)
