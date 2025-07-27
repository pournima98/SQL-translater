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

    if request.method == "POST":
        question = request.form.get("question")
        query = generate_sql_from_question(question)
        session['query'] = query  # <--- this was missing!
        try:
            df = pd.read_sql(query, engine)
            result = df.to_html(classes="table table-bordered", index=False)
        except Exception as e:
            result = f"<p style='color:red;'>Error: {str(e)}</p>"

    return render_template("index.html", result=result, query=query)

@app.route("/report", methods=["GET"])
def report():
    query = session.get('query')
    if not query:
        return "No query found. Submit a question first.", 400

    try:
        chart_data_uri = generate_chart_base64(query, engine)
        return render_template("report_template.html", chart_path=chart_data_uri)
    except Exception as e:
        return f"Error generating chart: {e}", 500

if __name__ == "__main__":
    app.run(debug=True)
