FROM mcr.microsoft.com/playwright:v1.61.1-jammy

WORKDIR /tests
COPY deploy/compose/integration/frontend-check.mjs ./frontend-check.mjs

# Keep the browser used by the integration gate pinned to the version used by
# FrontEnd's functional suite. The base image already provides its browsers.
RUN npm install --no-save --ignore-scripts @playwright/test@1.61.1

CMD ["node", "frontend-check.mjs"]
