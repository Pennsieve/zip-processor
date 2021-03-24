# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# TEST IMAGE
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FROM pennsieve/base-processor-pandas-test:1-5800e81 as test

WORKDIR /app

COPY zip_processor/zip_processor /app/zip_processor
COPY zip_processor/tests /app/tests
COPY zip_processor/requirements.txt /app/requirements.txt
COPY zip_processor/run.py /app/run.py

RUN pip install --upgrade pip && pip install -r requirements.txt

ENTRYPOINT [""]

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# PRODUCTION IMAGE
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

FROM pennsieve/base-processor-pandas-test:1-5800e81 as prod

WORKDIR /app

COPY zip_processor/zip_processor /app/zip_processor
COPY zip_processor/tests /app/tests
COPY zip_processor/requirements.txt /app/requirements.txt
COPY zip_processor/run.py /app/run.py

RUN pip install --upgrade pip && pip install -r requirements.txt

ENTRYPOINT [""]
