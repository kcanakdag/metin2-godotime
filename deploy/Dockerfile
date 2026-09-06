FROM clockworklabs/spacetime:v2.8.3@sha256:31f6d1d754f821362cec7e39e3680dd2efeb7a57f3ed0eb36c4cca1f12f46bb3
USER root
RUN mkdir -p /data && chown 1000:1000 /data && chmod 700 /data
USER spacetime
ENV XDG_CONFIG_HOME=/data/config
COPY mt2_server.wasm /game/mt2_server.wasm
CMD ["start", "--listen-addr", "0.0.0.0:3000", "--data-dir", "/data", "--page_pool_max_size", "536870912", "--non-interactive"]
