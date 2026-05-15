FROM python:3.12-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .

RUN uv sync --frozen \
    && git init \
    && git add -A \
    && git -c user.name=build -c user.email=build@localhost commit --allow-empty -m "build" \
    && uv run --group dev python -m mkdocs build --strict --site-dir _site/docs \
    && cp -r website/* _site/

FROM nginx:alpine

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf \
    && chown -R nginx:nginx /var/cache/nginx /var/log/nginx

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/_site /usr/share/nginx/html

USER nginx

EXPOSE 3000