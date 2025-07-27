# utils/charts.py
import io
import base64
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")  # for headless environments (no GUI)
import pandas as pd

def generate_chart_base64(query, engine):
    df = pd.read_sql(query, engine)

    if df.empty:
        raise ValueError("Query returned no data to plot.")

    fig, ax = plt.subplots()

    # Handle chart based on column types
    if df.shape[1] >= 2:
        x = df.iloc[:, 0]
        y = df.iloc[:, 1]
        ax.plot(x, y, marker='o')
        ax.set_xlabel(str(df.columns[0]))
        ax.set_ylabel(str(df.columns[1]))
        ax.set_title("Generated Chart")
    else:
        raise ValueError("Need at least two columns to plot.")

    buf = io.BytesIO()
    fig.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)
    chart_uri = "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    return chart_uri

