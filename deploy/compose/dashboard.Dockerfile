FROM node:22-alpine

WORKDIR /opt/silicium/dashboard

COPY Network/silicium-layer-dashboard/package*.json ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts

COPY Network/silicium-layer-dashboard/ ./
RUN npm run build

EXPOSE 5174
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5174"]
