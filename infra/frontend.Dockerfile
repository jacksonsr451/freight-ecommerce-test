FROM node:24-alpine

WORKDIR /app/frontend
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
COPY frontend/package.json frontend/package-lock.json ./
RUN chown -R node:node /app
USER node
RUN npm ci
COPY --chown=node:node frontend/ ./

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
