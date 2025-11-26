import { Request, Response } from 'express';
import { EnrollmentService } from '../services/enrollment.service';
import { NotificationService } from '../services/notification.service';

export default class TechnicianController {
    private enrollmentService: EnrollmentService;
    private notificationService: NotificationService;

    constructor() {
        this.enrollmentService = new EnrollmentService();
        this.notificationService = new NotificationService();
    }

    // ========================================
    // SUBMIT ENROLLMENT
    // ========================================
    public async submitEnrollment(req: Request, res: Response): Promise<void> {
        try {
            const enrollmentData = req.body;

            // Process & stage enrollment
            const enrollment = await this.enrollmentService.submitEnrollment(enrollmentData);

            // Notify admin (async, don't block response)
            this.notificationService.notifyAdminOfNewEnrollment(enrollment);

            // Respond to client
            res.status(201).json({
                message: "Enrollment submitted successfully",
                enrollmentId: enrollment.id,
                status: enrollment.status
            });
        } catch (error: any) {
            res.status(400).json({
                message: "Error submitting enrollment",
                error: error.message
            });
        }
    }

    // ========================================
    // GET TECHNICIAN RECORDS (OPTIONAL)
    // This could later pull from DashboardService
    // ========================================
    public async getTechnicianRecords(req: Request, res: Response): Promise<void> {
        try {
            // Not implemented yet; placeholder for dashboard integration
            res.status(200).json({ message: "Record lookup not implemented" });
        } catch (error: any) {
            res.status(500).json({ message: "Failed to fetch technician records" });
        }
    }
}
