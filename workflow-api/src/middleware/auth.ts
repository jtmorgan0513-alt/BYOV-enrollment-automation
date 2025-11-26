import { Request, Response, NextFunction } from 'express';

export const authMiddleware = (req: Request, res: Response, next: NextFunction) => {

    const adminKey = process.env.ADMIN_KEY;

    if (!adminKey) {
        console.warn("WARNING: ADMIN_KEY is not set in environment variables.");
    }

    const providedKey = req.headers['x-admin-key'];

    if (!providedKey) {
        return res.status(401).json({ message: "Admin key missing." });
    }

    if (providedKey !== adminKey) {
        return res.status(403).json({ message: "Invalid admin key." });
    }

    // Key is valid → allow access
    next();
};
