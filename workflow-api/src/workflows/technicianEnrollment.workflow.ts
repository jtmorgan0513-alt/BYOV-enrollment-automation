import { EnrollmentService } from '../services/enrollment.service';
import { NotificationService } from '../services/notification.service';
import { EmailService } from '../services/email.service';
import { DashboardService } from '../services/dashboard.service';

class TechnicianEnrollmentWorkflow {
    private enrollmentService: EnrollmentService;
    private notificationService: NotificationService;
    private emailService: EmailService;
    private dashboardService: DashboardService;

    constructor() {
        this.enrollmentService = new EnrollmentService();
        this.notificationService = new NotificationService();
        this.emailService = new EmailService();
        this.dashboardService = new DashboardService();
    }

    public async submitEnrollment(enrollmentData: any) {
        const existingOnDashboard = await this.dashboardService.checkExistingRecord(enrollmentData.techId);
        if (existingOnDashboard) {
            throw new Error('Technician already exists on dashboard.');
        }

        const enrollment = await this.enrollmentService.submitEnrollment(enrollmentData);
        await this.notificationService.notifyAdminOfNewEnrollment(enrollment);
        return enrollment;
    }

    public async reviewEnrollment(enrollmentId: string, approval: boolean, adminName: string) {
        const enrollment = this.enrollmentService.getEnrollmentById(enrollmentId);
        if (!enrollment) {
            throw new Error('Enrollment not found.');
        }

        if (approval) {
            const approved = this.enrollmentService.approveEnrollment(enrollmentId, adminName);
            if (!approved) throw new Error('Failed to approve enrollment.');
            const created = await this.dashboardService.createTechnicianRecord(approved);
            if (created && created.id) {
                try {
                    await this.dashboardService.patchTechnicianRecord(created.id, approved);
                } catch (e) {
                    console.warn('Patch technician record failed', e);
                }
            }
            await this.notificationService.notifyTechOfApproval(approved.email, approved.name);
            return approved;
        } else {
            const rejected = this.enrollmentService.rejectEnrollment(enrollmentId, adminName);
            if (!rejected) throw new Error('Failed to reject enrollment.');
            await this.notificationService.notifyTechOfRejection(rejected.email, rejected.name);
            return rejected;
        }
    }
}

export default TechnicianEnrollmentWorkflow;