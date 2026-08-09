import React, { createContext, useContext, useState, useEffect } from "react";

export type RoleType = "drafter" | "reviewer" | "approver" | "admin";

export interface UserProfile {
  role: RoleType;
  name: string;
  title: string;
  department: string;
  canEdit: boolean;
  canShare: boolean;
  canFinalize: boolean;
  canAdmin: boolean;
}

export const ROLE_PROFILES: Record<RoleType, UserProfile> = {
  drafter: {
    role: "drafter",
    name: "Sanjay R. Deshmukh",
    title: "Drafting Officer",
    department: "Higher & Technical Education Dept",
    canEdit: true,
    canShare: true,
    canFinalize: true,
    canAdmin: false,
  },
  reviewer: {
    role: "reviewer",
    name: "Anjali P. Kulkarni",
    title: "Desk Officer / Employee",
    department: "Higher & Technical Education Dept",
    canEdit: false,
    canShare: false,
    canFinalize: false,
    canAdmin: false,
  },
  approver: {
    role: "approver",
    name: "Dr. Rajesh V. Patil",
    title: "Joint Secretary / Approver",
    department: "General Administration Dept",
    canEdit: false,
    canShare: false,
    canFinalize: true,
    canAdmin: false,
  },
  admin: {
    role: "admin",
    name: "Priya N. Joshi",
    title: "System Administrator",
    department: "General Administration Dept",
    canEdit: false,
    canShare: false,
    canFinalize: false,
    canAdmin: true,
  },
};

interface RoleContextValue {
  activeRole: RoleType;
  profile: UserProfile;
  switchRole: (role: RoleType) => void;
}

const RoleContext = createContext<RoleContextValue>({
  activeRole: "drafter",
  profile: ROLE_PROFILES.drafter,
  switchRole: () => {},
});

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeRole, setActiveRole] = useState<RoleType>(() => {
    const saved = localStorage.getItem("app_user_role");
    return (saved as RoleType) || "drafter";
  });

  const switchRole = (role: RoleType) => {
    setActiveRole(role);
    localStorage.setItem("app_user_role", role);
  };

  const profile = ROLE_PROFILES[activeRole] || ROLE_PROFILES.drafter;

  return (
    <RoleContext.Provider value={{ activeRole, profile, switchRole }}>
      {children}
    </RoleContext.Provider>
  );
};

export const useUserRole = () => useContext(RoleContext);
