# pgvector is not bundled in the stock TimescaleDB image.
FROM timescale/timescaledb:2.17.2-pg15 AS vector-build
USER root
RUN apk add --no-cache --virtual .build-deps build-base clang15 llvm15-dev git \
    && git clone --branch v0.8.0 --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector && make OPTFLAGS="" && make install

FROM timescale/timescaledb:2.17.2-pg15
COPY --from=vector-build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --from=vector-build /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
