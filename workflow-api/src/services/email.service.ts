import nodemailer from 'nodemailer';
import sgMail from '@sendgrid/mail';

export class EmailService {
    private transporter;
    private sendgridEnabled: boolean;
    private disabled: boolean;

    constructor() {
        this.disabled = process.env.EMAIL_DISABLED === '1' || process.env.EMAIL_DISABLED === 'true';
        const sgKey = process.env.SENDGRID_API_KEY;
        this.sendgridEnabled = !!sgKey;
        if (this.sendgridEnabled) {
            sgMail.setApiKey(sgKey as string);
        }
        this.transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: process.env.EMAIL_USER,
                pass: process.env.EMAIL_PASS,
            }
        });
    }

    // ========================================
    // Base Email Method
    // ========================================
    public async sendEmail(to: string, subject: string, message: string): Promise<void> {
        if (this.disabled) {
            console.log(`[EMAIL_DISABLED] Skipping email to ${to}: ${subject}`);
            return;
        }
        if (this.sendgridEnabled) {
            const fromEmail = process.env.SENDGRID_FROM_EMAIL || process.env.EMAIL_USER;
            try {
                await sgMail.send({
                    to,
                    from: fromEmail as string,
                    subject,
                    text: message
                });
                console.log(`[SendGrid] Email sent to ${to}: ${subject}`);
                return;
            } catch (error: any) {
                console.error('[SendGrid] Error sending email, falling back to SMTP:', error.response?.body || error.message || error);
            }
        }

        // Fallback SMTP via nodemailer
        const mailOptions = {
            from: process.env.EMAIL_USER,
            to,
            subject,
            text: message
        };

        try {
            await this.transporter.sendMail(mailOptions);
            console.log(`(SMTP) Email sent to ${to}: ${subject}`);
        } catch (error: any) {
            console.error('(SMTP) Error sending email:', error.message || error);
            throw new Error('Email sending failed');
        }
    }

    // ========================================
    // Wrapper: Approval Email
    // ========================================
    public async sendApprovalEmail(email: string, technicianName: string): Promise<void> {
        const subject = "Your BYOV Enrollment Has Been Approved";
        const message = `
Hi ${technicianName},

Your BYOV enrollment has been APPROVED.

You are now authorized for the Bring Your Own Vehicle program.

Thank you.
        `;

        await this.sendEmail(email, subject, message);
    }

    // ========================================
    // Wrapper: Rejection Email
    // ========================================
    public async sendRejectionEmail(email: string, technicianName: string): Promise<void> {
        const subject = "Your BYOV Enrollment Has Been Rejected";
        const message = `
Hi ${technicianName},

Your BYOV enrollment has been REJECTED.

For additional details, please contact your supervisor.

Thank you.
        `;

        await this.sendEmail(email, subject, message);
    }
}
