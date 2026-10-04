import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';

export const participants = sqliteTable('participants', {
  id: text('id').primaryKey(),
  tokenHash: text('token_hash').notNull().unique(),
  profile: text('profile').notNull(),
  createdAt: text('created_at').notNull(),
});
export const reviews = sqliteTable('reviews', {
  id: text('id').primaryKey(),
  participantId: text('participant_id').notNull().references(() => participants.id),
  mapId: text('map_id').notNull(),
  phase: text('phase').notNull(),
  payload: text('payload').notNull(),
  receivedAt: text('received_at').notNull(),
}, table => [index('idx_reviews_participant').on(table.participantId), index('idx_reviews_map').on(table.mapId)]);
export const requestLimits = sqliteTable('request_limits', {
  key: text('key').primaryKey(),
  count: integer('count').notNull(),
  expiresAt: integer('expires_at').notNull(),
});
