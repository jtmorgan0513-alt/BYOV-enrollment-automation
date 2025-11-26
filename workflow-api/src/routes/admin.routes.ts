import { Router } from 'express';
import AdminController from '../controllers/admin.controller';

const router = Router();
const adminController = new AdminController();

// ========================================
// GET ALL PENDING ENROLLMENTS
// ========================================
router.get('/enrollments', (req, res) =>
    adminController.getEnrollments(req, res)
);

// ========================================
// APPROVE ENROLLMENT
// POST /api/admin/enrollments/:id/approve
// ========================================
router.post('/enrollments/:id/approve', (req, res) =>
    adminController.approveEnrollment(req, res)
);

// ========================================
// REJECT ENROLLMENT
// POST /api/admin/enrollments/:id/reject
// ========================================
router.post('/enrollments/:id/reject', (req, res) =>
    adminController.rejectEnrollment(req, res)
);

export default router;
