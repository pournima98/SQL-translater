from sqlalchemy import create_engine
import pandas as pd
from faker import Faker
import random

# Connect to MySQL
# engine = create_engine('mysql+pymysql://root:Hemant@123@localhost/churn_analysis')
engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")


fake = Faker()

# customers data
customers = [{
  'customer_id': i,
  'name': fake.name(),
  'signup_date': fake.date_between(start_date='-3y', end_date='today'),
  'plan_id': random.randint(1, 3),
  'region_id': random.randint(1, 5)
} for i in range(1, 501)]
pd.DataFrame(customers).to_sql('customers', engine, if_exists='append', index=False)

# subscriptions data
subscriptions = [{
  'subscription_id': i,
  'customer_id': random.randint(1, 500),
  'start_date': fake.date_between(start_date='-3y', end_date='-1y'),
  'end_date': fake.date_between(start_date='-1y', end_date='today'),
  'is_active': random.choice([True, False])
} for i in range(1, 601)]
pd.DataFrame(subscriptions).to_sql('subscriptions', engine, if_exists='append', index=False)

# usage data
usage = [{
  'customer_id': random.randint(1, 500),
  'date': fake.date_between(start_date='-1y', end_date='today'),
  'logins': random.randint(0, 20),
  'sessions': random.randint(0, 50),
  'features_used': random.randint(1, 15)
} for _ in range(2000)]
pd.DataFrame(usage).to_sql('usage', engine, if_exists='append', index=False)

# support_tickets data
tickets = [{
  'ticket_id': i,
  'customer_id': random.randint(1, 500),
  'category': random.choice(['billing', 'technical', 'general']),
  'resolved': random.choice([True, False]),
  'time_to_resolve': random.randint(1, 72)  # hours
} for i in range(1, 1001)]
pd.DataFrame(tickets).to_sql('support_tickets', engine, if_exists='append', index=False)

# payments data
payments = [{
  'payment_id': i,
  'customer_id': random.randint(1, 500),
  'amount': round(random.uniform(20, 500), 2),
  'status': random.choice(['completed', 'failed', 'late']),
  'payment_date': fake.date_between(start_date='-1y', end_date='today')
} for i in range(1, 1501)]
pd.DataFrame(payments).to_sql('payments', engine, if_exists='append', index=False)

# plans data
plans = [
    {'plan_id': 1, 'plan_name': 'Basic', 'price': 49.99},
    {'plan_id': 2, 'plan_name': 'Standard', 'price': 99.99},
    {'plan_id': 3, 'plan_name': 'Premium', 'price': 199.99},
]
pd.DataFrame(plans).to_sql('plans', engine, if_exists='append', index=False)

# regions data
regions = [
    {'region_id': 1, 'region_name': 'North America'},
    {'region_id': 2, 'region_name': 'Europe'},
    {'region_id': 3, 'region_name': 'Asia'},
    {'region_id': 4, 'region_name': 'Australia'},
    {'region_id': 5, 'region_name': 'South America'},
]
pd.DataFrame(regions).to_sql('regions', engine, if_exists='append', index=False)

