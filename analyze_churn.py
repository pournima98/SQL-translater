from sqlalchemy import create_engine
import pandas as pd
from dotenv import load_dotenv
import os

from core.mysql_engine import get_db_connection

db_url = os.getenv("DB_URL")
engine = get_db_connection()
# Connect to MySQL
#engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

# Load churn-relevant joined data
query = """
SELECT c.customer_id,
    s.end_date,
    s.is_active,
    COALESCE(AVG(u.logins), 0) AS avg_logins,
    COALESCE(AVG(u.sessions), 0) AS avg_sessions,
    COALESCE(COUNT(DISTINCT t.ticket_id), 0) AS support_tickets,
    COALESCE(AVG(p.amount), 0) AS avg_payment
FROM customers c
JOIN subscriptions s ON c.customer_id = s.customer_id
LEFT JOIN usages u ON u.customer_id = c.customer_id
LEFT JOIN support_tickets t ON t.customer_id = c.customer_id
LEFT JOIN payments p ON p.customer_id = c.customer_id
GROUP BY c.customer_id, s.end_date, s.is_active
"""
df = pd.read_sql(query, engine)
print(df.head())

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

df['churned'] = df['is_active'].apply(lambda x: 0 if x else 1)
X = df[['avg_logins', 'avg_sessions', 'support_tickets', 'avg_payment']]
y = df['churned']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

model = LogisticRegression()
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
print("\nModel Performance:\n", classification_report(y_test, y_pred))

# Feature importance
for col, coef in zip(X.columns, model.coef_[0]):
    print(f"{col}: {coef:.4f}")
