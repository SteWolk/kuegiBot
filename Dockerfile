FROM continuumio/miniconda3:4.12.0

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python and all deps via conda (including ta-lib 0.4.19)
RUN conda install -c conda-forge \
    python=3.10 \
    ta-lib=0.4.19 \
    numpy=1.26.0 \
    pandas=2.2.1 \
    -y

# Install remaining packages via pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "backtest.py"]