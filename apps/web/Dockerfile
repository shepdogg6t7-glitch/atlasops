FROM node:24-slim

ENV NODE_ENV=production \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:3000

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --include=dev

COPY apps/web ./

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
