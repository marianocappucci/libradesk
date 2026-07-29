import { Pool } from 'pg';
import dotenv from 'dotenv';

dotenv.config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://usuario:password@localhost:5432/libradesk',
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});

pool.on('error', (err) => {
  console.error('Error en pool de conexiones:', err);
});

export default pool;

export async function testConnection() {
  try {
    const result = await pool.query('SELECT NOW()');
    console.log('✓ Conexión a BD exitosa:', result.rows[0]);
  } catch (error) {
    console.error('✗ Error de conexión a BD:', error);
    process.exit(1);
  }
}
