export interface Technician {
    id: string;
    name: string;
    email: string;
    phone: string;
    status: 'pending' | 'approved' | 'rejected';
    createdAt: Date;
    updatedAt: Date;
}

export interface EnrollmentRequest {
    name: string;
    email: string;
    phone: string;
}

export interface AdminNotification {
    technicianId: string;
    message: string;
    timestamp: Date;
}

export interface EmailNotification {
    to: string;
    subject: string;
    body: string;
}