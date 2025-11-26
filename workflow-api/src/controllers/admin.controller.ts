import { Request, Response } from 'express';
import { EnrollmentService } from '../services/enrollment.service';
import { NotificationService } from '../services/notification.service';
import { DashboardService } from '../services/dashboard.service';

export default class AdminController {
    private enrollmentService: EnrollmentService;
    private notificationService: NotificationService;
    private dashboardService: DashboardService;

    constructor() {
        this.enrollmentService = new EnrollmentService();
        this.notificationService = new NotificationService();
        this.dashboardService = new DashboardService();
    }

    // ========================================
    // GET ALL PENDING ENROLLMENTS
    // ========================================
    public getEnrollments = (req: Request, res: Response): void => {
        try {
            const pending = this.enrollmentService.getAllPending();
            res.status(200).json(pending);
        } catch (error: any) {
            res.status(500).json({
                message: "Failed to fetch pending enrollments",
                error: error.message
            });
        }
    };

    // ========================================
    // APPROVE ENROLLMENT
    // ========================================
    public approveEnrollment = async (req: Request, res: Response): Promise<void> => {
        try {
            const { id } = req.params;
            const adminName = req.body.approvedBy || "Admin";

            const approvedRecord = this.enrollmentService.approveEnrollment(id, adminName);

            if (!approvedRecord) {
                res.status(404).json({ message: "Enrollment not found or already processed" });
                return;
            }

            // Push to BYOV Dashboard
            await this.dashboardService.createTechnicianRecord(approvedRecord);

            // Notify technician
            await this.notificationService.notifyTechOfApproval(
                approvedRecord.email,
                approvedRecord.name
            );

            res.status(200).json({
                message: "Enrollment approved successfully",
                enrollment: approvedRecord
            });

        } catch (error: any) {
            res.status(500).json({
                message: "Error approving enrollment",
                error: error.message
            });
        }
    };

    // ========================================
    // REJECT ENROLLMENT
    // ========================================
    public rejectEnrollment = async (req: Request, res: Response): Promise<void> => {
        try {
            const { id } = req.params;
            const adminName = req.body.rejectedBy || "Admin";

            const rejectedRecord = this.enrollmentService.rejectEnrollment(id, adminName);

            if (!rejectedRecord) {
                res.status(404).json({ message: "Enrollment not found or already processed" });
                return;
            }

            // Notify technician
            await this.notificationService.notifyTechOfRejection(
                rejectedRecord.email,
                rejectedRecord.name
            );

            res.status(200).json({
                message: "Enrollment rejected successfully",
                enrollment: rejectedRecord
            });

        } catch (error: any) {
            res.status(500).json({
                message: "Error rejecting enrollment",
                error: error.message
            });
        }
    };
}
