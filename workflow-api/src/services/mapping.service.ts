import { Enrollment } from '../models/technician.model';

export interface DashboardTechnicianPayload {
  name: string;
  techId: string;
  district: string;
  region: string;
  vinNumber: string;
  vehicleMake: string;
  vehicleModel: string;
  vehicleYear: string;
  insuranceExpiration: string;
  registrationExpiration: string;
  techEmail: string;
  enrollmentStatus: string;
  comments?: string;
  dateStartedByov?: string;
}

export function mapEnrollmentToDashboard(enrollment: Enrollment): DashboardTechnicianPayload {
  return {
    name: enrollment.name,
    techId: enrollment.techId,
    district: enrollment.district || 'UNKNOWN',
    region: enrollment.region || 'UNKNOWN',
    vinNumber: enrollment.vehicle?.vin || '',
    vehicleMake: enrollment.vehicle?.make || '',
    vehicleModel: enrollment.vehicle?.model || '',
    vehicleYear: enrollment.vehicle?.year || '',
    insuranceExpiration: enrollment.insurance?.expiresOn || '',
    registrationExpiration: enrollment.registrationExpiration || '',
    techEmail: enrollment.email,
    enrollmentStatus: 'Enrollment in Process',
    comments: `Workflow submission ${enrollment.id}`
  };
}

export function mapEnrollmentApprovedToPatch(enrollment: Enrollment): Partial<DashboardTechnicianPayload> {
  return {
    enrollmentStatus: 'Enrolled',
    dateStartedByov: new Date().toISOString().slice(0,10)
  };
}
