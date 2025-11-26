import { Router } from 'express';
import TechnicianController from '../controllers/technician.controller';

const router = Router();
const technicianController = new TechnicianController();

// ========================================
// SUBMIT ENROLLMENT
// POST /api/technicians/enroll
// ========================================
router.post('/enroll', (req, res) =>
    technicianController.submitEnrollment(req, res)
);

// ========================================
// GET TECHNICIAN RECORDS (Optional)
// GET /api/technicians/records
// ========================================
router.get('/records', (req, res) =>
    technicianController.getTechnicianRecords(req, res)
);

export default router;
