FROM node:20-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package*.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=false
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME=${NEXT_PUBLIC_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME}

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
