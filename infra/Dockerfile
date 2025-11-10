FROM solanalabs/solana:stable

# Conserver les chemins attendus par docker-compose
ENV HOME=/home/solana
WORKDIR /home/solana

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Script d'entrée qui enveloppe solana / solana-validator
COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint \
    && mkdir -p /home/solana/.silicium/ledger /home/solana/.config/solana

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]
