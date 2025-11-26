import { v4 as uuidv4 } from 'uuid';
import {
    Enrollment,
    PendingEnrollments,
    ApprovedEnrollments,
    RejectedEnrollments
} from '../models/technician.model';

export class EnrollmentService {

    // ================================
    // 1. PROCESS NEW ENROLLMENT
    // ================================
    public async submitEnrollment(data: any): Promise<Enrollment> {

        // Required fields
        const required = [
            'techId', 'name', 'email', 'phone',
            'vehicle', 'insurance', 'acknowledgements'
        ];

        for (const field of required) {
            if (!data[field]) {
                throw new Error(`Missing required field: ${field}`);
            }
        }

        // Prevent duplicates (techId must be unique)
        const duplicate = this.findEnrollmentByTechId(data.techId);
        if (duplicate) {
            throw new Error(`Technician ${data.techId} already has an enrollment.`);
        }

        // Build clean enrollment object (include optional district/region/registrationExpiration)
        const enrollment: Enrollment = {
            id: uuidv4(),
            techId: data.techId,
            name: data.name,
            email: data.email,
            phone: data.phone,
            district: data.district,
            region: data.region,
            vehicle: data.vehicle,
            insurance: data.insurance,
            registrationExpiration: data.registrationExpiration,
            mileageRate: data.mileageRate || "0.57",
            acknowledgements: data.acknowledgements,
            photos: data.photos || [],
            status: 'pending',
            submittedAt: new Date()
        };

        // Save to pending storage
        PendingEnrollments.set(enrollment.id, enrollment);

        return enrollment;
    }

    // ================================
    // 2. GET ALL PENDING ENROLLMENTS
    // ================================
    public getAllPending(): Enrollment[] {
        return Array.from(PendingEnrollments.values());
    }

    // ================================
    // 3. GET ENROLLMENT BY ID
    // ================================
    public getEnrollmentById(id: string): Enrollment | undefined {
        return PendingEnrollments.get(id)
            || ApprovedEnrollments.get(id)
            || RejectedEnrollments.get(id);
    }

    // ================================
    // 4. APPROVE ENROLLMENT
    // ================================
    public approveEnrollment(id: string, adminName: string): Enrollment | null {
        const record = PendingEnrollments.get(id);
        if (!record) return null;

        record.status = 'approved';
        record.approvedAt = new Date();
        record.approvedBy = adminName;

        PendingEnrollments.delete(id);
        ApprovedEnrollments.set(id, record);

        return record;
    }

    // ================================
    // 5. REJECT ENROLLMENT
    // ================================
    public rejectEnrollment(id: string, adminName: string): Enrollment | null {
        const record = PendingEnrollments.get(id);
        if (!record) return null;

        record.status = 'rejected';
        record.approvedAt = new Date(); 
        record.approvedBy = adminName;

        PendingEnrollments.delete(id);
        RejectedEnrollments.set(id, record);

        return record;
    }

    // ================================
    // 6. CHECK DUPLICATE TECH ID
    // ================================
    private findEnrollmentByTechId(techId: string): Enrollment | undefined {
        const all = [
            ...PendingEnrollments.values(),
            ...ApprovedEnrollments.values(),
            ...RejectedEnrollments.values()
        ];

        return all.find(e => e.techId === techId);
    }
}
