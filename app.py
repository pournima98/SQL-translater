from sqlalchemy import create_engine
import pandas as pd
from utils.charts import generate_chart_base64
from langchain_agent import generate_sql_from_question
from flask import Flask, request, render_template, session
from dotenv import load_dotenv
import os

load_dotenv()  # loads variables from .env into environment

app = Flask(__name__)
app.secret_key = os.environ.get("OPENAI_API_KEY")

engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    query = None
    chart_data_uri = None

    if request.method == "POST":
        question = request.form.get("question")
        query = generate_sql_from_question(question)
        session['query'] = query

        try:
            df = pd.read_sql(query, engine)
            result = df.to_html(classes="table table-bordered", index=False)
            chart_data_uri = generate_chart_base64(query, engine)
        except Exception as e:
            result = f"<p style='color:red;'>Error: {str(e)}</p>"

    return render_template("index.html", result=result, query=query, chart_path=chart_data_uri)

