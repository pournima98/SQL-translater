from flask import Flask, request, render_template
from langchain_agent import generate_sql_from_question
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)
engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    query = None

    if request.method == "POST":
        question = request.form.get("question")
        query = generate_sql_from_question(question)
        try:
            df = pd.read_sql(query, engine)
            result = df.to_html(classes="table table-bordered", index=False)
        except Exception as e:
            result = f"<p style='color:red;'>Error: {str(e)}</p>"

    return render_template("index.html", result=result, query=query)

if __name__ == "__main__":
    app.run(debug=True)
