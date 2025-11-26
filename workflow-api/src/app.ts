import express from 'express';
import bodyParser from 'body-parser';
import technicianRoutes from './routes/technician.routes';
import adminRoutes from './routes/admin.routes';
import { logger } from './utils/logger';
import { authMiddleware } from './middleware/auth';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

app.use('/api/technicians', technicianRoutes);
app.use('/api/admin', authMiddleware, adminRoutes);

app.listen(PORT, () => {
    logger.info(`Server is running on port ${PORT}`);
});