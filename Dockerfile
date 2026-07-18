FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

COPY . .
RUN npm install

RUN npm run build

EXPOSE 3000

CMD ["sh", "-c", "HOST=0.0.0.0 NITRO_HOST=0.0.0.0 npm run preview"]

