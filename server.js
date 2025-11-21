// server.js
import express from 'express';
import cors from 'cors';
import path from 'path';

const app = express();
const PORT = process.env.PORT || 3000;

// Servir tu carpeta pública (donde están index.html y los HTML de mapas)
app.use(express.static(path.join(__dirname, 'public')));
app.use(cors());

// Endpoint SSE
app.get('/events', (req, res) => {
  res.set({
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive'
  });
  res.flushHeaders();

  // Función para emitir un evento cada vez que lleguen nuevos datos.
  // Aquí simulamos con un timer de 60 s.
  const interval = setInterval(() => {
    const now = new Date().toISOString();
    res.write(`data: ${now}\n\n`);
  }, 60_000);

  // Limpiar al cerrar conexión
  req.on('close', () => {
    clearInterval(interval);
    res.end();
  });
});

// Arrancar servidor
app.listen(PORT, () => {
  console.log(`Servidor SSE escuchando en http://localhost:${PORT}`);
});

