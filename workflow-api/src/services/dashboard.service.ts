import { mapEnrollmentToDashboard, mapEnrollmentApprovedToPatch } from './mapping.service';

export class DashboardService {
    private apiUrl: string;
    private disabled: boolean;

    constructor() {
        // Real BYOV Dashboard URL (use env var if you want)
        this.apiUrl = process.env.BYOV_DASHBOARD_API_URL 
            || "https://byovdashboard.replit.app/api";
        this.disabled = process.env.DASHBOARD_DISABLED === '1' || process.env.DASHBOARD_DISABLED === 'true';
    }

    // ========================================
    // POST APPROVED ENROLLMENT TO DASHBOARD
    // ========================================
    public async createTechnicianRecord(enrollment: any): Promise<any> {
        if (this.disabled) {
            console.log('[DASHBOARD_DISABLED] Skipping push to dashboard');
            return { ok: true, simulated: true, techId: enrollment.techId };
        }
        const payload = mapEnrollmentToDashboard(enrollment);

        try {
            const response = await fetch(`${this.apiUrl}/technicians`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(
                    `Dashboard rejected record: ${response.status} — ${errorText}`
                );
            }

            return await response.json();

        } catch (error: any) {
            console.error("Failed to create dashboard technician record:", error);
            throw new Error("Dashboard push failed");
        }
    }

    // ========================================
    // GET TECHNICIAN RECORDS (Optional)
    // ========================================
    public async getTechnicianRecords(): Promise<any[]> {
        if (this.disabled) {
            console.log('[DASHBOARD_DISABLED] Skipping fetch technician records');
            return [];
        }
        try {
            const response = await fetch(`${this.apiUrl}/technicians`);
            if (!response.ok) throw new Error("Failed to fetch records");

            return await response.json();

        } catch (error: any) {
            console.error("Error fetching technician records:", error);
            return [];
        }
    }

    // ========================================
    // CHECK IF TECH EXISTS (duplicate prevention)
    // ========================================
    public async checkExistingRecord(techId: string): Promise<any | null> {
        if (this.disabled) {
            console.log('[DASHBOARD_DISABLED] Skipping duplicate check');
            return null;
        }
        try {
            const response = await fetch(`${this.apiUrl}/technicians?techId=${encodeURIComponent(techId)}`);
            if (!response.ok) throw new Error("Dashboard lookup failed");
            const arr = await response.json();
            if (Array.isArray(arr) && arr.length > 0) return arr[0];
            return null;

        } catch (error: any) {
            console.error("Error checking dashboard duplicate:", error);
            return null;
        }
    }

    // ========================================
    // PATCH TECHNICIAN RECORD AFTER APPROVAL
    // ========================================
    public async patchTechnicianRecord(id: string, enrollment: any): Promise<any> {
        if (this.disabled) {
            console.log('[DASHBOARD_DISABLED] Skipping patch to dashboard');
            return { ok: true, simulated: true, id };
        }
        const payload = mapEnrollmentApprovedToPatch(enrollment);
        try {
            const response = await fetch(`${this.apiUrl}/technicians/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Dashboard patch failed: ${response.status} — ${errorText}`);
            }
            return await response.json();
        } catch (error: any) {
            console.error('Failed to patch dashboard technician record:', error);
            throw new Error('Dashboard patch failed');
        }
    }
}
