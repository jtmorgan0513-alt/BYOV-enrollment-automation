import { EmailService } from './email.service';
import { Enrollment } from '../models/technician.model';

export class NotificationService {
    private emailService: EmailService;
    private adminEmail: string;

    constructor() {
        this.emailService = new EmailService();
        this.adminEmail = process.env.ADMIN_EMAIL || 'admin@example.com';
    }

    // ========================================
    // Notify Admin of New Enrollment
    // ========================================
    public async notifyAdminOfNewEnrollment(enrollment: Enrollment): Promise<void> {
        const subject = `New BYOV Enrollment Submitted - ${enrollment.techId}`;
        const message = `
A new technician has submitted a BYOV enrollment.

Tech ID: ${enrollment.techId}
Name: ${enrollment.name}
Email: ${enrollment.email}
Phone: ${enrollment.phone}

Submission ID: ${enrollment.id}
Submitted At: ${enrollment.submittedAt.toISOString()}

Please log in to review the pending enrollment.
        `;

        try {
            await this.emailService.sendEmail(this.adminEmail, subject, message);
        } catch (error) {
            console.error("Failed to notify admin:", error);
        }
    }

    // ========================================
    // Notify Technician of Approval
    // ========================================
    public async notifyTechOfApproval(email: string, name: string): Promise<void> {
        const subject = "Your BYOV Enrollment Has Been Approved";
        const message = `
Hi ${name},

Your BYOV enrollment has been reviewed and APPROVED.

You are now authorized to participate in the Bring Your Own Vehicle program.

If you have any questions, please contact your supervisor.

Thank you.
        `;

        try {
            await this.emailService.sendEmail(email, subject, message);
        } catch (error) {
            console.error("Failed to notify technician:", error);
        }
    }

    // ========================================
    // Notify Technician of Rejection
    // ========================================
    public async notifyTechOfRejection(email: string, name: string): Promise<void> {
        const subject = "Your BYOV Enrollment Has Been Rejected";
        const message = `
Hi ${name},

Unfortunately, your BYOV enrollment has been reviewed and REJECTED.

Please reach out to your supervisor or program administrator for next steps.

Thank you.
        `;

        try {
            await this.emailService.sendEmail(email, subject, message);
        } catch (error) {
            console.error("Failed to notify technician:", error);
        }
    }
}
