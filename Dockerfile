FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the dependencies first. This layer is rebuilt only when pyproject.toml
# changes, not on every code change. The empty package lets setuptools resolve it.
COPY pyproject.toml ./
RUN mkdir routeiq && touch routeiq/__init__.py && pip install -e .

COPY routeiq ./routeiq
COPY configs ./configs
COPY data/prepare_clinc.py ./data/prepare_clinc.py

# Build the benchmark data and train the baseline model into the image.
# This downloads CLINC150 from Hugging Face, so the build needs network access.
RUN python data/prepare_clinc.py && python -m routeiq.train --config configs/clinc150.yaml

# Run as a normal user. The database lives on a volume.
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
ENV ROUTEIQ_DB=/data/routeiq.db
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import httpx2; httpx2.get('http://localhost:8000/health', timeout=3).raise_for_status()"

CMD ["uvicorn", "routeiq.api:app", "--host", "0.0.0.0", "--port", "8000"]
