import dotenv from 'dotenv';

dotenv.config();

const config = {
    port: process.env.PORT || 3000,
    db: {
        host: process.env.DB_HOST || 'localhost',
        port: process.env.DB_PORT || 5432,
        user: process.env.DB_USER || 'user',
        password: process.env.DB_PASSWORD || 'password',
        database: process.env.DB_NAME || 'technician_enrollment',
    },
    email: {
        service: process.env.EMAIL_SERVICE || 'gmail',
        user: process.env.EMAIL_USER || 'example@gmail.com',
        password: process.env.EMAIL_PASSWORD || 'password',
    },
    notification: {
        adminEmail: process.env.ADMIN_EMAIL || 'admin@example.com',
    },
};

export default config;