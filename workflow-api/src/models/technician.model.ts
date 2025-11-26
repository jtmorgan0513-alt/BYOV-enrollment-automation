// ================================
// BYOV Enrollment Data Interfaces
// ================================

export interface VehicleInfo {
    year: string;
    make: string;
    model: string;
    color: string;
    plate: string;
    vin: string;
    vinDecoded?: any;                // Optional decoded VIN details
}

export interface InsuranceInfo {
    provider: string;
    policyNumber: string;
    expiresOn: string;               // ISO date string (YYYY-MM-DD)
    cardPhotoUrl?: string;           // URL or Base64 image
}

export interface Acknowledgements {
    mileageRule: boolean;            // Confirms 35-minute commute rule
    byovPolicy: boolean;             // Confirms BYOV policy was reviewed
    signature: string;               // Digital signature or typed name
}

export interface Enrollment {
    id: string;                      // Unique enrollment ID (UUID)
    techId: string;                  // Unique Sears Technician ID
    name: string;
    email: string;
    phone: string;
    district?: string;               // District for technician
    region?: string;                 // Region for technician

    vehicle: VehicleInfo;
    insurance: InsuranceInfo;
    registrationExpiration?: string; // ISO date string for registration expiry

    mileageRate: string;             // Example: "0.57"
    acknowledgements: Acknowledgements;

    photos: string[];                // Array of image URLs/Base64

    status: 'pending' | 'approved' | 'rejected';

    submittedAt: Date;
    approvedAt?: Date;
    approvedBy?: string;
}

// ===================================
// In-Memory Storage for Development
// ===================================

export const PendingEnrollments: Map<string, Enrollment> = new Map();
export const ApprovedEnrollments: Map<string, Enrollment> = new Map();
export const RejectedEnrollments: Map<string, Enrollment> = new Map();
