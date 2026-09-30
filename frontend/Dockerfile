FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json* .npmrc ./
COPY frontend/package.json frontend/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/i18n/package.json packages/i18n/package.json
COPY packages/domain/package.json packages/domain/package.json
RUN npm ci
COPY frontend frontend
COPY packages packages
EXPOSE 3000
CMD ["npm", "run", "dev", "--workspace", "frontend"]
