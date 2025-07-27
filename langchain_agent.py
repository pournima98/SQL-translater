import os
# from langchain.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import openai

import os
openai.api_key = os.getenv("OPENAI_API_KEY")

llm = ChatOpenAI(temperature=0)

schema = """
You have access to the following MySQL schema:
customers(customer_id, name, signup_date, plan_id, region_id)
subscriptions(subscription_id, customer_id, start_date, end_date, is_active)
usage(customer_id, date, logins, sessions, features_used)
support_tickets(ticket_id, customer_id, category, resolved, time_to_resolve)
payments(payment_id, customer_id, amount, status, payment_date)
"""

prompt_template = PromptTemplate.from_template("""
Given the following schema:
{schema}

Translate this user question into an SQL query:
Question: {question}

SQL:
""")

def generate_sql_from_question(question: str) -> str:
    prompt = prompt_template.format(schema=schema, question=question)
    response = llm.predict(prompt)
    return response.strip()
